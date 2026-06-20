import threading
import customtkinter as ctk
from qbot.ui.styles import COLORS, FONTS
from qbot.ai_generator import AIGenerator
from qbot.test_runner import TestRunner, TestResult
from qbot.page_crawler import PageCrawler
from qbot.test_linter import lint_test_code, format_issues
from qbot.bitbucket_client import BitbucketClient, format_code_context
from qbot import context_cache
from qbot.jira_client import TicketDetails
from qbot.config import config

# Max self-healing rounds: failed tests + their errors are sent back to the AI
# for a fix, then re-executed. Bounded to avoid infinite loops / token burn.
MAX_REPAIR_ROUNDS = 2

# Max lint -> AI-fix passes before generation gives up and runs the tests as-is.
# Each pass re-lints the corrected code; the loop stops early once it's clean.
MAX_LINT_PASSES = 2


class RunnerView(ctk.CTkFrame):
    """Pipeline: Crawl Pages -> AI Generates Tests -> Playwright Executes -> Report."""

    def __init__(self, parent, ticket: TicketDetails, ticket_text: str, on_back):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.ticket = ticket
        self.ticket_text = ticket_text
        self.on_back = on_back
        self.ai = AIGenerator()
        self.runner = TestRunner()
        self.crawler = PageCrawler(on_log=self._log_threadsafe)
        self.bitbucket = BitbucketClient(on_log=self._log_threadsafe)
        self.generated_code = ""
        self.page_context = ""
        self.code_context = ""
        self.exec_result = None
        self._cancelled = threading.Event()
        self._build_ui()
        self.after(500, self._run_pipeline)

    # ------------------------------------------------------------------
    #  UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        titlebar = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], height=35, corner_radius=0)
        titlebar.pack(fill="x")
        titlebar.pack_propagate(False)
        ctk.CTkLabel(
            titlebar, text="  QBot  -  Running Pipeline",
            font=FONTS["small"], text_color=COLORS["text_dim"],
        ).pack(side="left", padx=8)

        toolbar = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], height=44, corner_radius=0)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)

        ctk.CTkLabel(
            toolbar, text=f"{self.ticket.key}",
            font=FONTS["body_bold"], text_color=COLORS["accent"],
        ).pack(side="left", padx=16)
        ctk.CTkLabel(
            toolbar, text=f"- {self.ticket.summary[:70]}",
            font=FONTS["body"], text_color=COLORS["text_dim"],
        ).pack(side="left")

        self.back_btn = ctk.CTkButton(
            toolbar, text="<- New Ticket", width=110, height=28,
            font=FONTS["small"], fg_color=COLORS["bg_input"],
            hover_color=COLORS["btn_neutral"], text_color=COLORS["text"],
            corner_radius=4, command=self.on_back,
        )
        self.back_btn.pack(side="right", padx=8)

        self.cancel_btn = ctk.CTkButton(
            toolbar, text="■  Stop", width=90, height=28,
            font=FONTS["small"], fg_color=COLORS["btn_neutral"],
            hover_color=COLORS["btn_neutral_hover"], text_color=COLORS["text"],
            corner_radius=4, command=self._cancel,
        )
        self.cancel_btn.pack(side="right", padx=4)

        self.replay_btn = ctk.CTkButton(
            toolbar, text="▶  Replay Tests", width=120, height=28,
            font=FONTS["small"], fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"], text_color="white",
            corner_radius=4, command=self._replay_tests, state="disabled",
        )
        self.replay_btn.pack(side="right", padx=4)

        main = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"])
        main.pack(fill="both", expand=True, padx=15, pady=10)

        # Left panel: steps
        left = ctk.CTkFrame(
            main, fg_color=COLORS["bg_card"], corner_radius=6,
            border_color=COLORS["border"], border_width=1, width=270,
        )
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        ctk.CTkLabel(
            left, text="PIPELINE", font=FONTS["small"], text_color=COLORS["text_dim"],
        ).pack(padx=15, pady=(15, 10), anchor="w")

        self.steps = {}
        step_defs = [
            ("crawl",    "1. Crawl Pages (login)"),
            ("generate", "2. AI Generates Tests"),
            ("execute",  "3. Playwright Executes"),
            ("repair",   "4. AI Repairs Failures"),
            ("report",   "5. Final Report"),
        ]
        for key, label in step_defs:
            row = ctk.CTkFrame(left, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=4)
            ind = ctk.CTkLabel(row, text="..", font=FONTS["body"], width=28)
            ind.pack(side="left")
            lbl = ctk.CTkLabel(row, text=label, font=FONTS["body"],
                               text_color=COLORS["text_dim"], anchor="w")
            lbl.pack(side="left", padx=6)
            self.steps[key] = {"indicator": ind, "label": lbl}

        # Stats
        stats_box = ctk.CTkFrame(left, fg_color=COLORS["bg_input"], corner_radius=4)
        stats_box.pack(fill="x", padx=12, pady=(24, 6))
        ctk.CTkLabel(stats_box, text="RESULTS", font=FONTS["small"],
                     text_color=COLORS["text_dim"]).pack(padx=10, pady=(8, 4), anchor="w")

        self.stats_labels = {}
        for stat_key, stat_label, color in [
            ("passed",  "Passed:",  COLORS["passed"]),
            ("failed",  "Failed:",  COLORS["failed"]),
            ("skipped", "Skipped:", COLORS["skipped"]),
            ("total",   "Total:",   COLORS["text"]),
        ]:
            row = ctk.CTkFrame(stats_box, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=1)
            ctk.CTkLabel(row, text=stat_label, font=FONTS["body"],
                         text_color=color, width=70, anchor="w").pack(side="left")
            val = ctk.CTkLabel(row, text="-", font=FONTS["body_bold"], text_color=color)
            val.pack(side="left")
            self.stats_labels[stat_key] = val

        self.chrome_label = ctk.CTkLabel(
            left, text="", font=FONTS["small"], text_color=COLORS["text_dim"],
            wraplength=240,
        )
        self.chrome_label.pack(padx=12, pady=(8, 4))

        # Right panel: output tabs
        right = ctk.CTkFrame(
            main, fg_color=COLORS["bg_card"], corner_radius=6,
            border_color=COLORS["border"], border_width=1,
        )
        right.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(right, text="OUTPUT", font=FONTS["small"],
                     text_color=COLORS["text_dim"]).pack(padx=15, pady=(12, 4), anchor="w")

        self.tabview = ctk.CTkTabview(
            right,
            fg_color=COLORS["bg_input"],
            segmented_button_fg_color=COLORS["bg_card"],
            segmented_button_selected_color=COLORS["accent"],
            segmented_button_unselected_color=COLORS["bg_card"],
            segmented_button_selected_hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"],
            command=self._on_tab_change,
        )
        self.tabview.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self._tab_names = ("Live Log", "Page Context", "Generated Tests", "Test Results")
        for tab in self._tab_names:
            self.tabview.add(tab)
        self._on_tab_change()

        def _tb(tab_name):
            tb = ctk.CTkTextbox(
                self.tabview.tab(tab_name),
                font=FONTS["mono_small"],
                fg_color=COLORS["bg_dark"],
                text_color=COLORS["text"],
                wrap="word",
            )
            tb.pack(fill="both", expand=True)
            return tb

        self.log_text     = _tb("Live Log")
        self.context_text = _tb("Page Context")
        self.code_text    = _tb("Generated Tests")
        self.results_text = _tb("Test Results")

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------
    def _log(self, msg: str):
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.update()

    def _log_threadsafe(self, msg: str):
        self.after(0, lambda: self._log(msg))

    def _set_step(self, key: str, status: str):
        icons  = {"running": ">>", "done": "OK", "error": "!!", "pending": "..", "cancelled": "XX"}
        colors = {
            "running":   COLORS["warning"],
            "done":      COLORS["success"],
            "error":     COLORS["error"],
            "pending":   COLORS["text_dim"],
            "cancelled": COLORS["error"],
        }
        self.steps[key]["indicator"].configure(text=icons.get(status, ".."))
        self.steps[key]["label"].configure(text_color=colors.get(status, COLORS["text_dim"]))
        self.update()

    def _update_stats(self, result: TestResult):
        for key in ("passed", "failed", "skipped", "total"):
            self.stats_labels[key].configure(text=str(getattr(result, key)))
        self.update()

    def _on_tab_change(self, *_args):
        """Update tab text colors: white on selected (accent), dark on unselected."""
        current = self.tabview.get()
        for name, btn in self.tabview._segmented_button._buttons_dict.items():
            if name == current:
                btn.configure(text_color=COLORS["btn_text"])
            else:
                btn.configure(text_color=COLORS["text"])

    def _cancel(self):
        self._cancelled.set()
        self.cancel_btn.configure(state="disabled", text="Stopping...")
        self.after(0, lambda: self._log("\nCancellation requested."))

    # ------------------------------------------------------------------
    #  Pipeline
    # ------------------------------------------------------------------
    def _run_pipeline(self):
        threading.Thread(target=self._pipeline_worker, daemon=True).start()

    def _pipeline_worker(self):
        try:
            self._step_crawl()
            if self._cancelled.is_set():
                self._mark_cancelled(after="crawl")
                return
            self._step_generate()
            if self._cancelled.is_set():
                self._mark_cancelled(after="generate")
                return
            self._step_execute()
            if self._cancelled.is_set():
                self._mark_cancelled(after="execute")
                return
            self._step_repair()
            if self._cancelled.is_set():
                self._mark_cancelled(after="repair")
                return
            self._step_report()
        except Exception as e:
            err_msg = str(e)
            self.after(0, lambda msg=err_msg: self._log(f"\nPipeline error: {msg}"))
        finally:
            is_stopped = self._cancelled.is_set()
            self.after(0, lambda: self.cancel_btn.configure(
                state="normal",
                text="Stopped" if is_stopped else "✔ Done",
                fg_color=COLORS["btn_neutral"] if is_stopped else COLORS["btn_run"],
                hover_color=COLORS["btn_neutral_hover"] if is_stopped else COLORS["btn_run_hover"],
                text_color=COLORS["text"] if is_stopped else COLORS["btn_text"],
                command=self.on_back,
            ))
            if not is_stopped:
                self.cancel_btn._text_label.configure(fg="#ffffff")

    def _mark_cancelled(self, after: str):
        order = ["crawl", "generate", "execute", "repair", "report"]
        idx = order.index(after)
        for key in order[idx + 1:]:
            self.after(0, lambda k=key: self._set_step(k, "cancelled"))
        self.after(0, lambda: self._log("\nPipeline cancelled."))

    # -- Step 1: Crawl pages ------------------------------------------
    def _step_crawl(self):
        self.after(0, lambda: self._set_step("crawl", "running"))

        # Fresh cached context for this ticket? Skip the crawl entirely.
        cached = context_cache.load_context(self.ticket.key, config.target_base_url or "")
        if cached:
            snapshots, code_context, age = cached
            self.crawler.snapshots = snapshots
            self.page_context = self.crawler.get_snapshots_text()
            self.code_context = code_context
            mins = int(age // 60)
            self.after(0, lambda: self._log(
                f"Step 1: Using cached crawl from {mins} min ago — "
                f"{len(snapshots)} page(s), {len(code_context):,} chars of code context.\n"
                f"   (Cache expires after 60 min; it is reused only while auth_state.json exists.)"
            ))
            self.after(0, lambda: self._set_step("crawl", "done"))

            def _show_cached():
                self.context_text.delete("1.0", "end")
                ctx = self.page_context or "(No pages captured)"
                if self.code_context:
                    ctx += f"\n\n{'=' * 60}\n\n{self.code_context}"
                self.context_text.insert("1.0", ctx)
            self.after(0, _show_cached)
            return

        self.after(0, lambda: self._log(
            "Step 1: Crawling target pages...\n"
            "   Chrome will open. If you see a login page, please log in.\n"
            "   After login, the crawler will visit pages from the ticket.\n"
        ))

        try:
            self.crawler.crawl(self.ticket_text)
            self.page_context = self.crawler.get_snapshots_text()

            n_pages = len(self.crawler.snapshots)
            self.after(0, lambda: self._log(
                f"\nCrawl complete: {n_pages} pages captured"
            ))

            # Fetch code changes from Bitbucket (if configured)
            if self.bitbucket.is_configured():
                self.after(0, lambda: self._log("\nFetching code changes from Bitbucket..."))
                try:
                    changes = self.bitbucket.get_ticket_changes(self.ticket.key)
                    self.code_context = format_code_context(changes)
                    if changes.commits:
                        self.after(0, lambda: self._log(f"   {changes.summary}"))
                    else:
                        self.after(0, lambda: self._log(f"   {changes.summary}"))
                except Exception as e:
                    err_msg = str(e)
                    self.after(0, lambda msg=err_msg: self._log(f"   Bitbucket fetch failed: {msg} (continuing without code context)"))
                    self.code_context = ""

            # Cache crawl + code context for fast re-runs of this ticket
            context_cache.save_context(
                self.ticket.key, config.target_base_url or "",
                self.crawler.snapshots, self.code_context,
            )

            self.after(0, lambda: self._set_step("crawl", "done"))

            def _show():
                self.context_text.delete("1.0", "end")
                ctx = self.page_context or "(No pages captured)"
                if self.code_context:
                    ctx += f"\n\n{'=' * 60}\n\n{self.code_context}"
                self.context_text.insert("1.0", ctx)
            self.after(0, _show)

        except Exception as e:
            err_msg = str(e)
            self.after(0, lambda: self._set_step("crawl", "error"))
            self.after(0, lambda msg=err_msg: self._log(f"Crawl failed: {msg}"))
            raise

    # -- Step 2: AI generates tests -----------------------------------
    def _step_generate(self):
        self.after(0, lambda: self._set_step("generate", "running"))
        self.after(0, lambda: self._log("\nStep 2: AI is generating tests from real page context..."))
        provider = config.ai_provider
        model = config.github_model
        self.after(0, lambda: self._log(f"   Provider: {provider}  Model: {model}"))
        self.after(0, lambda: self._log(f"   Page context: {len(self.page_context)} chars from {len(self.crawler.snapshots)} pages"))
        if self.code_context:
            self.after(0, lambda: self._log(f"   Code context: {len(self.code_context):,} chars from Bitbucket"))

        try:
            self.generated_code = self.ai.generate_tests(
                self.ticket_text,
                config.target_base_url,
                page_context=self.page_context,
                code_context=self.code_context,
                on_log=self._log_threadsafe,
            )

            # Lint against the real DOM snapshots; fix flagged issues with the
            # AI before ever executing. Loop up to MAX_LINT_PASSES times so a
            # fix that leaves (or introduces) issues gets another attempt,
            # stopping early as soon as the code lints clean.
            issues = lint_test_code(self.generated_code, self.crawler.snapshots)
            if not issues:
                self.after(0, lambda: self._log("   Linter: no issues found."))
            else:
                for lint_pass in range(1, MAX_LINT_PASSES + 1):
                    n_err = sum(1 for i in issues if i.severity == "error")
                    n_warn = len(issues) - n_err
                    self.after(0, lambda p=lint_pass, e=n_err, w=n_warn: self._log(
                        f"   Linter pass {p}/{MAX_LINT_PASSES}: {e} error(s), {w} warning(s):"))
                    for issue in issues[:15]:
                        line = str(issue)
                        self.after(0, lambda l=line: self._log(f"      {l}"))

                    issues_text = format_issues(issues)
                    self.after(0, lambda: self._log("   Asking AI to fix flagged issues..."))
                    try:
                        self.generated_code = self.ai.fix_lint_issues(
                            self.generated_code, issues_text, self.page_context)
                    except Exception as fix_err:
                        msg = str(fix_err)
                        self.after(0, lambda m=msg: self._log(
                            f"   Lint fix failed ({m}) — continuing with current code."))
                        break

                    issues = lint_test_code(self.generated_code, self.crawler.snapshots)
                    n_rem_err = sum(1 for i in issues if i.severity == "error")
                    self.after(0, lambda e=n_rem_err, tot=len(issues): self._log(
                        f"   Lint fix applied ({e} error(s) remaining of {tot} issue(s))."))

                    if not issues:
                        self.after(0, lambda: self._log("   Linter: all issues resolved."))
                        break
                else:
                    self.after(0, lambda n=len(issues): self._log(
                        f"   Linter: {n} issue(s) remain after {MAX_LINT_PASSES} passes — continuing."))

            filepath = self.runner.write_test_file(self.generated_code)

            if self.runner.chrome_path:
                self.after(0, lambda: self.chrome_label.configure(
                    text="Chrome found", text_color=COLORS["success"]))
            else:
                self.after(0, lambda: self.chrome_label.configure(
                    text="Chrome not found", text_color=COLORS["warning"]))

            self.after(0, lambda: self._log(f"Tests written: {filepath}"))
            self.after(0, lambda: self._set_step("generate", "done"))

            def _show():
                self.code_text.delete("1.0", "end")
                self.code_text.insert("1.0", self.generated_code)
            self.after(0, _show)

        except Exception as e:
            err_msg = str(e)
            self.after(0, lambda: self._set_step("generate", "error"))
            self.after(0, lambda msg=err_msg: self._log(f"Generation failed: {msg}"))
            raise

    # -- Step 3: Playwright executes ----------------------------------
    def _step_execute(self):
        self.after(0, lambda: self._set_step("execute", "running"))
        self.after(0, lambda: self._log(
            "\nStep 3: Executing tests...\n"
            "   Auth state from crawl step will be reused.\n"
            "   If session expired, you may need to log in again."
        ))

        result = self.runner.run_tests()
        self.exec_result = result

        self.after(0, lambda: self._update_stats(result))
        icon = "PASS" if result.success else "FAIL"
        self.after(0, lambda: self._log(
            f"\n{icon}: {result.passed} passed, {result.failed} failed, "
            f"{result.errors} errors, {result.skipped} skipped"
        ))
        self.after(0, lambda: self._set_step("execute", "done" if result.success else "error"))

        self.after(0, lambda: self._show_results(result))

    # -- Step 4: Self-healing repair loop ------------------------------
    def _step_repair(self):
        result = self.exec_result
        if not result or result.success or not result.individual_results:
            self.after(0, lambda: self._set_step("repair", "done"))
            if result and result.success:
                self.after(0, lambda: self._log("\nStep 4: All tests passed — no repair needed."))
            return

        self.after(0, lambda: self._set_step("repair", "running"))

        # Master view of every test keyed by name. Each repair round re-runs
        # ONLY the failing tests and merges their fresh results back in here, so
        # already-passing tests are never re-executed and can't be re-broken.
        merged = {t["name"]: t for t in result.individual_results}

        for round_no in range(1, MAX_REPAIR_ROUNDS + 1):
            if self._cancelled.is_set():
                return

            failures = [t for t in merged.values()
                        if t["status"] in ("FAILED", "ERROR")]
            if not failures:
                break

            self.after(0, lambda r=round_no, n=len(failures): self._log(
                f"\nStep 4: Repair round {r}/{MAX_REPAIR_ROUNDS} — "
                f"sending {n} failing test(s) + errors back to the AI..."))

            try:
                fixed_code = self.ai.repair_tests(
                    self.ticket_text, self.generated_code, failures, self.page_context)
            except Exception as e:
                msg = str(e)
                self.after(0, lambda m=msg: self._log(f"   Repair failed: {m} — keeping last results."))
                break

            self.generated_code = fixed_code
            self.runner.write_test_file(fixed_code)

            def _show_code():
                self.code_text.delete("1.0", "end")
                self.code_text.insert("1.0", self.generated_code)
            self.after(0, _show_code)

            if self._cancelled.is_set():
                return

            # Re-run ONLY the previously-failing tests (by pytest node id)
            # instead of the whole suite — faster and avoids re-touching passes.
            node_ids = [t["node_id"] for t in failures if t.get("node_id")]
            self.after(0, lambda n=len(node_ids) or len(failures): self._log(
                f"   Re-running {n} repaired test(s)..."))

            subset = (self.runner.run_tests(node_ids=node_ids)
                      if node_ids else self.runner.run_tests())

            if subset.total == 0:
                # Node ids no longer resolve (a fix renamed or deleted tests) —
                # fall back to a full run and rebuild the picture from scratch.
                self.after(0, lambda: self._log(
                    "   (targeted re-run matched no tests — running full suite)"))
                subset = self.runner.run_tests()
                merged = {t["name"]: t for t in subset.individual_results}
            else:
                for t in subset.individual_results:
                    merged[t["name"]] = t

            result = self._aggregate_results(merged, subset.output)
            self.exec_result = result

            self.after(0, lambda r=result: self._update_stats(r))
            icon = "PASS" if result.success else "FAIL"
            self.after(0, lambda r=result, i=icon: self._log(
                f"   {i}: {r.passed} passed, {r.failed} failed, "
                f"{r.errors} errors, {r.skipped} skipped"))
            self.after(0, lambda r=result: self._show_results(r))

            if result.success:
                self.after(0, lambda: self._log("   All tests pass after repair."))
                break

        final = self.exec_result
        self.after(0, lambda: self._set_step(
            "repair", "done" if (final and final.success) else "error"))
        self.after(0, lambda: self._set_step(
            "execute", "done" if (final and final.success) else "error"))

    @staticmethod
    def _aggregate_results(merged: dict, output: str) -> TestResult:
        """Rebuild an aggregate TestResult from the merged per-test map after a
        targeted repair re-run (only the failing subset was actually executed)."""
        items = list(merged.values())
        passed = sum(1 for t in items if t["status"] == "PASSED")
        failed = sum(1 for t in items if t["status"] == "FAILED")
        errors = sum(1 for t in items if t["status"] == "ERROR")
        skipped = sum(1 for t in items if t["status"] == "SKIPPED")
        total = len(items)
        return TestResult(
            passed=passed, failed=failed, errors=errors, skipped=skipped,
            total=total, output=output,
            success=(failed == 0 and errors == 0 and total > 0),
            individual_results=items,
        )

    def _show_results(self, result: TestResult):
        self.results_text.delete("1.0", "end")

        # Header
        total = result.passed + result.failed + result.errors + result.skipped
        status = "ALL TESTS PASSED" if result.success else "SOME TESTS FAILED"
        self.results_text.insert("end", f"  {status}\n")
        self.results_text.insert("end", f"  {result.passed} passed  |  {result.failed} failed  |  {total} total\n")
        self.results_text.insert("end", f"{'─' * 50}\n\n")

        # Passed tests
        passed_tests = [t for t in result.individual_results if t["status"] == "PASSED"]
        if passed_tests:
            self.results_text.insert("end", "  ✓  PASSED\n\n")
            for tr in passed_tests:
                name = tr["name"].replace("test_", "").replace("_", " ").title()
                self.results_text.insert("end", f"      ✓  {name}\n")
            self.results_text.insert("end", "\n")

        # Failed tests
        failed_tests = [t for t in result.individual_results if t["status"] == "FAILED"]
        if failed_tests:
            self.results_text.insert("end", "  ✗  FAILED\n\n")
            for tr in failed_tests:
                name = tr["name"].replace("test_", "").replace("_", " ").title()
                self.results_text.insert("end", f"      ✗  {name}\n")
                if tr.get("message"):
                    self.results_text.insert("end", f"         → {tr['message']}\n")
            self.results_text.insert("end", "\n")

        # Skipped tests
        skipped_tests = [t for t in result.individual_results if t["status"] in ("SKIPPED", "ERROR")]
        if skipped_tests:
            self.results_text.insert("end", "  ○  SKIPPED / ERROR\n\n")
            for tr in skipped_tests:
                name = tr["name"].replace("test_", "").replace("_", " ").title()
                self.results_text.insert("end", f"      ○  {name}\n")
            self.results_text.insert("end", "\n")

        # Raw output (for debugging failures)
        if result.output and result.output.strip():
            self.results_text.insert("end", f"{'─' * 50}\n")
            self.results_text.insert("end", "  RAW OUTPUT\n\n")
            self.results_text.insert("end", result.output[-2000:] + "\n")

    # -- Step 4: Report -----------------------------------------------
    def _step_report(self):
        self.after(0, lambda: self._set_step("report", "running"))

        final = self.exec_result
        usage = self.ai.usage_report()
        if final:
            summary = (
                f"\n{'=' * 50}\n"
                f"PIPELINE COMPLETE\n"
                f"{'=' * 50}\n"
                f"Ticket : {self.ticket.key}\n"
                f"Summary: {self.ticket.summary}\n"
                f"Results: {final.passed} passed  |  {final.failed} failed  |  {final.errors} errors\n"
                f"Tests  : {self.runner.test_dir}\n"
                + (f"{usage}\n" if usage else "")
                + f"{'=' * 50}"
            )
        else:
            summary = "\nPipeline complete."
            if usage:
                summary += f"\n{usage}"

        self.after(0, lambda: self._log(summary))
        self.after(0, lambda: self._set_step("report", "done"))
        self.after(0, lambda: self.replay_btn.configure(state="normal"))
        self.after(200, lambda: self.tabview.set("Test Results"))

    # -- Replay tests -------------------------------------------------
    def _replay_tests(self):
        self.replay_btn.configure(state="disabled", text="Running...")

        def _do_replay():
            self.after(0, lambda: self._log("\n\nReplaying tests...\n"))
            self.after(0, lambda: self._set_step("execute", "running"))

            result = self.runner.run_tests()
            self.exec_result = result

            self.after(0, lambda: self._update_stats(result))
            icon = "PASS" if result.success else "FAIL"
            self.after(0, lambda: self._log(
                f"\n{icon}: {result.passed} passed, {result.failed} failed, "
                f"{result.errors} errors, {result.skipped} skipped"
            ))
            self.after(0, lambda: self._set_step("execute", "done" if result.success else "error"))
            self.after(0, lambda: self._show_results(result))
            self.after(0, lambda: self.replay_btn.configure(state="normal", text="▶  Replay Tests"))
            self.after(200, lambda: self.tabview.set("Test Results"))

        threading.Thread(target=_do_replay, daemon=True).start()
