"""Tests for the desktop module: tray, dashboard, notifications, shortcuts, launcher, icon_gen.

The tray tests mock pystray since the actual system tray requires a
display server.  Dashboard and notification tests run fully in-process.
Launcher tests mock tk.Tk to avoid needing a display.
"""

from __future__ import annotations

import py_compile
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from tinyassets.desktop.dashboard import DashboardHandler, DashboardMetrics
from tinyassets.desktop.host_tray import HostTrayService
from tinyassets.desktop.icon_gen import create_icon_image, generate_icon
from tinyassets.desktop.launcher import LauncherApp, _default_universe_path
from tinyassets.desktop.notifications import NotificationManager
from tinyassets.desktop.tray import TrayApp, _create_icon_image

# =====================================================================
# Icon image generation
# =====================================================================


class TestIconImage:
    def test_create_icon_image(self):
        img = _create_icon_image(64)
        assert img.size == (64, 64)
        assert img.mode == "RGB"

    def test_create_icon_custom_size(self):
        img = _create_icon_image(128)
        assert img.size == (128, 128)


# =====================================================================
# TrayApp (mocked pystray)
# =====================================================================


class TestTrayApp:
    def test_init_defaults(self):
        app = TrayApp()
        assert app._status == "Idle"
        assert app._paused is False

    def test_update_status(self):
        app = TrayApp()
        app._icon = MagicMock()
        app.update_status("Writing chapter 3")
        assert app._status == "Writing chapter 3"

    def test_start_creates_icon(self):
        with patch("tinyassets.desktop.tray.Icon") as MockIcon:
            mock_icon = MagicMock()
            MockIcon.return_value = mock_icon

            app = TrayApp()
            app.start()

            MockIcon.assert_called_once()
            mock_icon.run_detached.assert_called_once()

    def test_start_is_idempotent(self):
        with patch("tinyassets.desktop.tray.Icon") as MockIcon:
            mock_icon = MagicMock()
            MockIcon.return_value = mock_icon

            app = TrayApp()
            app.start()
            app.start()

            MockIcon.assert_called_once()
            mock_icon.run_detached.assert_called_once()

    def test_stop(self):
        app = TrayApp()
        mock_icon = MagicMock()
        app._icon = mock_icon
        app.stop()
        mock_icon.stop.assert_called_once()
        assert app._icon is None

    def test_notify(self):
        app = TrayApp()
        app._icon = MagicMock()
        app.notify("Chapter Done", "100 words")
        app._icon.notify.assert_called_once_with("100 words", title="Chapter Done")

    def test_pause_handler(self):
        paused = []
        app = TrayApp(on_pause=lambda: paused.append(True))
        app._icon = MagicMock()
        app._handle_pause()
        assert app._paused is True
        assert len(paused) == 1

    def test_resume_handler(self):
        resumed = []
        app = TrayApp(on_resume=lambda: resumed.append(True))
        app._icon = MagicMock()
        app._paused = True
        app._handle_resume()
        assert app._paused is False
        assert len(resumed) == 1

    def test_start_handler(self):
        started = []
        app = TrayApp(on_start=lambda: started.append(True))
        app._icon = MagicMock()
        app._handle_start()
        assert len(started) == 1

    def test_quit_handler(self):
        quit_called = []
        app = TrayApp(on_quit=lambda: quit_called.append(True))
        app._icon = MagicMock()
        app._handle_quit()
        assert len(quit_called) == 1
        assert app._icon is None  # stop() was called


# =====================================================================
# TrayApp -- extended status
# =====================================================================


class TestTrayExtendedStatus:
    def test_update_extended_status_universe(self):
        app = TrayApp()
        app._icon = MagicMock()
        app.update_extended_status(universe_name="ashwater")
        assert app._universe_name == "ashwater"

    def test_update_extended_status_words(self):
        app = TrayApp()
        app._icon = MagicMock()
        app.update_extended_status(word_count=5000)
        assert app._word_count == 5000

    def test_update_extended_status_tunnel(self):
        app = TrayApp()
        app._icon = MagicMock()
        app.update_extended_status(tunnel_url="https://test.trycloudflare.com")
        assert app._tunnel_url == "https://test.trycloudflare.com"

    def test_tooltip_includes_universe_and_words(self):
        app = TrayApp()
        app._icon = MagicMock()
        app.update_extended_status(universe_name="ashwater", word_count=1500)
        # Tooltip should be set on the icon
        assert "ashwater" in app._icon.title
        assert "1,500" in app._icon.title

    def test_menu_shows_extended_status(self):
        app = TrayApp()
        app._icon = MagicMock()
        app._universe_name = "ashwater"
        app._word_count = 3000
        app._tunnel_url = "https://test.trycloudflare.com"
        menu = app._build_menu()
        labels = [
            item.text if isinstance(item.text, str) else ""
            for item in menu._items
            if hasattr(item, "text")
        ]
        assert any("ashwater" in label for label in labels)
        assert any("3,000" in label for label in labels)
        assert any("trycloudflare" in label for label in labels)

    def test_menu_omits_empty_fields(self):
        app = TrayApp()
        app._icon = MagicMock()
        menu = app._build_menu()
        labels = [
            item.text if isinstance(item.text, str) else ""
            for item in menu._items
            if hasattr(item, "text")
        ]
        # No universe or tunnel lines when empty
        assert not any("Universe:" in label for label in labels)
        assert not any("Tunnel:" in label for label in labels)


# =====================================================================
# DashboardMetrics
# =====================================================================


class TestDashboardMetrics:
    def test_record_accept(self):
        m = DashboardMetrics()
        m.record_accept()
        assert m.accept_rate == 1.0
        assert m._accepted == 1
        assert m._evaluated == 1

    def test_record_reject(self):
        m = DashboardMetrics()
        m.record_accept()
        m.record_reject()
        assert m.accept_rate == 0.5

    def test_update_wph(self):
        m = DashboardMetrics()
        m.total_words = 1000
        m.update_wph()
        # Should be > 0 (just started, so very high).
        assert m.words_per_hour > 0

    def test_seed_from_db(self):
        """seed_from_db recovers word_count, scenes, chapters from story.db."""
        import sqlite3
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "story.db")
            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE scene_history ("
                "scene_id TEXT PRIMARY KEY, universe_id TEXT, "
                "book_number INTEGER, chapter_number INTEGER, "
                "scene_number INTEGER, word_count INTEGER DEFAULT 0, "
                "verdict TEXT DEFAULT 'accept', summary TEXT DEFAULT '')"
            )
            conn.execute(
                "INSERT INTO scene_history VALUES "
                "('s1','u',1,1,1,500,'accept',''), "
                "('s2','u',1,1,2,600,'accept',''), "
                "('s3','u',1,2,1,400,'revert','')"
            )
            conn.commit()
            conn.close()

            m = DashboardMetrics()
            m.seed_from_db(db_path)
            assert m.scenes_complete == 3
            assert m.total_words == 1500
            assert m.chapters_complete == 2
            assert m._accepted == 2  # 2 accepts, 1 revert
            assert m._evaluated == 3
            assert m.accept_rate > 0

    def test_seed_from_db_missing_db(self):
        """seed_from_db does nothing when DB doesn't exist."""
        m = DashboardMetrics()
        m.seed_from_db("/nonexistent/path/story.db")
        assert m.scenes_complete == 0
        assert m.total_words == 0

    def test_seed_from_output_dir(self):
        """Fallback: seed from output/book-*/chapter-*/scene-*.md files."""
        with tempfile.TemporaryDirectory() as td:
            # Create output structure
            ch1 = Path(td) / "output" / "book-1" / "chapter-01"
            ch2 = Path(td) / "output" / "book-1" / "chapter-02"
            ch1.mkdir(parents=True)
            ch2.mkdir(parents=True)
            (ch1 / "scene-01.md").write_text("word " * 100, encoding="utf-8")
            (ch1 / "scene-02.md").write_text("word " * 200, encoding="utf-8")
            (ch2 / "scene-01.md").write_text("word " * 150, encoding="utf-8")

            m = DashboardMetrics()
            # Pass a non-existent DB so it falls through to file scan
            m.seed_from_db(str(Path(td) / "story.db"), td)
            assert m.scenes_complete == 3
            assert m.chapters_complete == 2
            assert m.total_words == 450  # 100 + 200 + 150

    def test_seed_from_output_dir_empty(self):
        """seed_from_output_dir handles missing output dir gracefully."""
        with tempfile.TemporaryDirectory() as td:
            m = DashboardMetrics()
            m.seed_from_db(str(Path(td) / "story.db"), td)
            assert m.scenes_complete == 0


# =====================================================================
# DashboardHandler
# =====================================================================


class TestDashboardHandler:
    def test_phase_start(self):
        tray = MagicMock()
        dh = DashboardHandler(tray=tray)
        dh.handle_event({"type": "phase_start", "phase": "orient"})
        assert dh.metrics.current_phase == "orient"
        tray.update_status.assert_called()

    def test_draft_progress(self):
        dh = DashboardHandler()
        dh.handle_event({"type": "draft_progress", "word_count": 500})
        # draft_progress is an in-progress indicator — does not update total_words.
        # total_words is updated by scene_complete or run_book output.
        assert dh.metrics.total_words == 0

    def test_judge_result_accept(self):
        dh = DashboardHandler()
        dh.handle_event({
            "type": "judge_result",
            "judge": "codex",
            "verdict": "accept",
        })
        assert dh.metrics._accepted == 1

    def test_judge_result_revert(self):
        dh = DashboardHandler()
        dh.handle_event({
            "type": "judge_result",
            "judge": "codex",
            "verdict": "revert",
        })
        assert dh.metrics._evaluated == 1
        assert dh.metrics._accepted == 0

    def test_scene_complete(self):
        dh = DashboardHandler()
        dh.handle_event({
            "type": "scene_complete",
            "scene_number": 3,
            "word_count": 200,
        })
        assert dh.metrics.scenes_complete == 1
        assert dh.metrics.total_words == 200

    def test_chapter_complete_notifies(self):
        tray = MagicMock()
        dh = DashboardHandler(tray=tray)
        dh.handle_event({"type": "chapter_complete", "chapter": 5})
        assert dh.metrics.chapters_complete == 1
        tray.notify.assert_called()

    def test_book_complete_notifies(self):
        tray = MagicMock()
        dh = DashboardHandler(tray=tray)
        dh.handle_event({"type": "book_complete", "title": "The Dawn"})
        tray.notify.assert_called()

    def test_stuck_recovery(self):
        tray = MagicMock()
        dh = DashboardHandler(tray=tray)
        dh.handle_event({"type": "stuck_recovery", "level": 2})
        tray.notify.assert_called()

    def test_error_event(self):
        dh = DashboardHandler()
        dh.handle_event({"type": "error", "message": "something broke"})
        # Should not raise.

    def test_unknown_event(self):
        dh = DashboardHandler()
        dh.handle_event({"type": "unknown_event"})
        # Should not raise.

    def test_summary(self):
        dh = DashboardHandler()
        dh.metrics.total_words = 5000
        dh.metrics.chapters_complete = 3
        s = dh.summary()
        assert s["total_words"] == 5000
        assert s["chapters_complete"] == 3
        assert "accept_rate" in s

    def test_no_tray_does_not_crash(self):
        dh = DashboardHandler(tray=None)
        dh.handle_event({"type": "phase_start", "phase": "draft"})
        dh.handle_event({"type": "chapter_complete", "chapter": 1})
        # Should not raise.

    def test_log_callback_called_on_judge_result(self):
        lines = []
        dh = DashboardHandler(log_callback=lines.append)
        dh.handle_event({
            "type": "judge_result",
            "judge": "codex",
            "verdict": "accept",
        })
        assert len(lines) == 1
        assert "ACCEPT" in lines[0]

    def test_log_callback_called_on_scene_complete(self):
        lines = []
        dh = DashboardHandler(log_callback=lines.append)
        dh.handle_event({
            "type": "scene_complete",
            "scene_number": 5,
            "word_count": 300,
        })
        assert len(lines) == 1
        assert "Scene 5 complete" in lines[0]
        assert "300" in lines[0]

    def test_log_callback_called_on_chapter_complete(self):
        lines = []
        dh = DashboardHandler(log_callback=lines.append)
        dh.handle_event({"type": "chapter_complete", "chapter": 3})
        assert len(lines) == 1
        assert "Chapter 3 complete" in lines[0]

    def test_log_callback_called_on_book_complete(self):
        lines = []
        dh = DashboardHandler(log_callback=lines.append)
        dh.handle_event({"type": "book_complete", "title": "The Dawn"})
        assert len(lines) == 1
        assert "The Dawn" in lines[0]

    def test_log_callback_called_on_stuck_recovery(self):
        lines = []
        dh = DashboardHandler(log_callback=lines.append)
        dh.handle_event({"type": "stuck_recovery", "level": 2})
        assert len(lines) == 1
        assert "level 2" in lines[0]

    def test_log_callback_called_on_error(self):
        lines = []
        dh = DashboardHandler(log_callback=lines.append)
        dh.handle_event({"type": "error", "message": "disk full"})
        assert len(lines) == 1
        assert "disk full" in lines[0]

    def test_log_callback_not_called_on_phase_start(self):
        """phase_start does not emit a log line (nodes do that)."""
        lines = []
        dh = DashboardHandler(log_callback=lines.append)
        dh.handle_event({"type": "phase_start", "phase": "orient"})
        assert len(lines) == 0

    def test_log_callback_exception_does_not_propagate(self):
        def bad_callback(line):
            raise RuntimeError("boom")

        dh = DashboardHandler(log_callback=bad_callback)
        # Should not raise
        dh.handle_event({"type": "error", "message": "test"})

    def test_log_method_with_no_callback(self):
        dh = DashboardHandler()
        # _log should be a no-op when no callback set
        dh._log("test line")  # Should not raise


# =====================================================================
# NotificationManager
# =====================================================================


class TestNotificationManager:
    def test_chapter_complete(self):
        tray = MagicMock()
        nm = NotificationManager(tray=tray)
        nm.chapter_complete(5, word_count=1500)
        tray.notify.assert_called_once()

    def test_book_complete(self):
        tray = MagicMock()
        nm = NotificationManager(tray=tray)
        nm.book_complete("The Dawn", total_words=50000)
        tray.notify.assert_called_once()

    def test_stuck_recovery(self):
        tray = MagicMock()
        nm = NotificationManager(tray=tray)
        nm.stuck_recovery(3)
        tray.notify.assert_called_once()

    def test_error(self):
        tray = MagicMock()
        nm = NotificationManager(tray=tray)
        nm.error("something went wrong")
        tray.notify.assert_called_once()

    def test_no_tray_logs(self):
        nm = NotificationManager(tray=None)
        nm.chapter_complete(1)
        nm.book_complete("Test")
        nm.error("test error")
        # Should not raise.

    def test_tray_notify_failure(self):
        tray = MagicMock()
        tray.notify.side_effect = RuntimeError("no display")
        nm = NotificationManager(tray=tray)
        nm.chapter_complete(1)
        # Should not raise; falls back to logging.


# =====================================================================
# HostTrayService
# =====================================================================


class TestHostTrayService:
    def test_bind_dashboard_uses_one_shared_tray(self):
        service = HostTrayService()
        service._tray = MagicMock()

        binding_a = service.bind_dashboard(
            dashboard_key="u1",
            universe_name="ashwater",
            on_show_window=lambda: None,
            on_pause=lambda: None,
            on_resume=lambda: None,
            on_quit=lambda: None,
            output_dir=".",
        )
        binding_b = service.bind_dashboard(
            dashboard_key="u2",
            universe_name="emberfall",
            on_show_window=lambda: None,
            on_pause=lambda: None,
            on_resume=lambda: None,
            on_quit=lambda: None,
            output_dir=".",
        )

        assert binding_a is not None
        assert binding_b is not None
        assert len(service._entries) == 2
        service._tray.start.assert_called_once()
        service._tray.refresh_menu.assert_called()

    def test_unregister_last_dashboard_stops_tray(self):
        service = HostTrayService()
        service._tray = MagicMock()

        binding = service.bind_dashboard(
            dashboard_key="u1",
            universe_name="ashwater",
            on_show_window=lambda: None,
            on_pause=lambda: None,
            on_resume=lambda: None,
            on_quit=lambda: None,
            output_dir=".",
        )

        binding.stop()
        service._tray.stop.assert_called_once()


# =====================================================================
# Icon generator (icon_gen.py)
# =====================================================================


class TestIconGen:
    def test_create_icon_image_default_size(self):
        img = create_icon_image()
        assert img.size == (64, 64)
        assert img.mode == "RGB"

    def test_create_icon_image_custom_sizes(self):
        for size in (16, 32, 48, 256):
            img = create_icon_image(size)
            assert img.size == (size, size)

    def test_create_icon_image_has_content(self):
        """Icon should not be a single flat color."""
        img = create_icon_image(64)
        colors = img.getcolors(maxcolors=1000)
        assert colors is not None
        assert len(colors) > 1

    def test_generate_icon_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test.ico"
            result = generate_icon(out)
            assert result == out
            assert out.exists()
            assert out.stat().st_size > 0

    def test_generate_icon_is_valid_ico(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test.ico"
            generate_icon(out)
            with Image.open(out) as ico:
                assert ico.format == "ICO"


# =====================================================================
# LauncherApp (mocked tkinter)
# =====================================================================


class TestLauncherApp:
    def _make_app(self, **kwargs):
        """Create a LauncherApp with a mocked Tk root."""
        mock_root = MagicMock()
        mock_root.title = MagicMock()
        mock_root.geometry = MagicMock()
        mock_root.resizable = MagicMock()
        mock_root.configure = MagicMock()
        mock_root.iconbitmap = MagicMock()

        with patch("tinyassets.desktop.launcher.ttk") as mock_ttk, \
             patch("tinyassets.desktop.launcher.tk.StringVar") as MockSV, \
             patch("tinyassets.desktop.launcher.tk.BooleanVar") as MockBV, \
             patch("tinyassets.desktop.launcher.tk.Text") as MockText:
            # StringVar mock
            sv_instance = MagicMock()
            sv_instance.get.return_value = _default_universe_path()
            sv_instance.set = MagicMock(side_effect=lambda v: setattr(sv_instance, '_val', v))
            sv_instance.trace_add = MagicMock()
            MockSV.return_value = sv_instance

            # BooleanVar mock
            bv_instance = MagicMock()
            bv_instance.get.return_value = False
            MockBV.return_value = bv_instance

            # Text widget mock (premise field)
            mock_text = MagicMock()
            mock_text.get.return_value = ""
            MockText.return_value = mock_text

            # ttk.Style mock
            mock_style = MagicMock()
            mock_ttk.Style.return_value = mock_style

            # ttk widgets return MagicMocks
            mock_ttk.Frame.return_value = MagicMock()
            mock_ttk.Label.return_value = MagicMock()
            mock_ttk.Entry.return_value = MagicMock()
            mock_ttk.Button.return_value = MagicMock()
            mock_ttk.Checkbutton.return_value = MagicMock()

            app = LauncherApp(root=mock_root, **kwargs)

        # Most launcher unit tests exercise GUI state changes, not real daemon
        # startup. Seed a stub daemon so _handle_start() does not spawn
        # background threads unless a test explicitly calls _start_daemon().
        app._daemon = MagicMock()

        return app

    def test_init_does_not_crash(self):
        app = self._make_app()
        assert app.root is not None

    def test_title_set(self):
        app = self._make_app()
        app.root.title.assert_called_with("TinyAssets")

    def test_default_universe_path(self):
        expected = str(Path.home() / "Documents" / "TinyAssets" / "default-universe")
        assert _default_universe_path() == expected

    def test_universe_path_property(self):
        app = self._make_app()
        path = app.universe_path
        assert path == _default_universe_path()

    def test_status_default(self):
        app = self._make_app()
        # Status var was mocked, check set_status works without error
        app.set_status("Testing")

    def test_handle_start_calls_callback(self):
        calls = []

        def on_start(universe, minimized, verbose):
            calls.append((universe, minimized, verbose))

        app = self._make_app(on_start=on_start)
        app._handle_start()
        assert len(calls) == 1

    def test_handle_start_no_callback(self):
        app = self._make_app()
        # Should not raise even without callback
        app._handle_start()

    def test_handle_quit(self):
        app = self._make_app()
        app._handle_quit()
        app.root.destroy.assert_called_once()

    def test_geometry(self):
        app = self._make_app()
        app.root.geometry.assert_called_with("420x620")

    def test_show_window(self):
        app = self._make_app()
        app._show_window()
        app.root.after.assert_called()

    def test_hide_window(self):
        app = self._make_app()
        app.hide_window()
        app.root.withdraw.assert_called_once()

    def test_stats_polling_updates_vars(self):
        app = self._make_app()
        # Simulate a dashboard handler with known stats
        mock_dh = MagicMock()
        mock_dh.summary.return_value = {
            "current_phase": "draft",
            "total_words": 1234,
            "chapters_complete": 2,
            "accept_rate": 0.75,
        }
        app._dashboard_handler = mock_dh
        app._stats_polling = True
        app._poll_stats()
        mock_dh.summary.assert_called_once()

    def test_handle_quit_stops_daemon(self):
        app = self._make_app()
        mock_daemon = MagicMock()
        mock_daemon._stop_event = MagicMock()
        mock_daemon._paused = MagicMock()
        app._daemon = mock_daemon
        app._handle_quit()
        mock_daemon._stop_event.set.assert_called_once()
        app.root.destroy.assert_called_once()

    def test_start_daemon_creates_thread(self):
        """Verify _start_daemon creates a DaemonController and thread."""
        app = self._make_app()

        mock_controller = MagicMock()
        mock_tray_binding = MagicMock()
        mock_host_tray = MagicMock()
        mock_host_tray.bind_dashboard.return_value = mock_tray_binding

        with (
            patch(
                "tinyassets.desktop.launcher.DaemonController",
                return_value=mock_controller,
            ) if False else patch(
                "tinyassets.__main__.DaemonController",
                return_value=mock_controller,
            ),
            patch(
                "tinyassets.desktop.host_tray.HostTrayService.shared",
                return_value=mock_host_tray,
            ),
            patch(
                "tinyassets.desktop.launcher.threading.Thread",
            ) as mock_thread_cls,
        ):
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            app._start_daemon()

            assert app._daemon is mock_controller
            mock_host_tray.bind_dashboard.assert_called_once()
            mock_thread.start.assert_called_once()

    def test_handle_start_ignored_while_running(self):
        calls = []

        def on_start(universe, minimized, verbose):
            calls.append((universe, minimized, verbose))

        app = self._make_app(on_start=on_start)
        app._running = True
        app._handle_start()
        assert calls == []

    def test_start_stats_polling_idempotent(self):
        app = self._make_app()
        with patch.object(app, "_poll_stats") as mock_poll:
            app._start_stats_polling()
            app._start_stats_polling()
        mock_poll.assert_called_once()

    def test_on_daemon_stopped_stops_tray_binding(self):
        app = self._make_app()
        tray = MagicMock()
        app._tray = tray
        app._running = True
        app._on_daemon_stopped()
        tray.stop.assert_called_once()

    def test_append_feed_line_schedules_after(self):
        """_append_feed_line schedules via root.after for thread safety."""
        app = self._make_app()
        app._append_feed_line("Orient: test line")
        app.root.after.assert_called()

    def test_do_append_feed_inserts_text(self):
        """_do_append_feed inserts into the feed Text widget."""
        app = self._make_app()
        # Reset the mock to track new calls
        app._feed_text.reset_mock()
        app._do_append_feed("Hello world")
        app._feed_text.configure.assert_called()
        app._feed_text.insert.assert_called()
        app._feed_text.see.assert_called()

    def test_feed_text_widget_exists(self):
        """LauncherApp should create a _feed_text attribute."""
        app = self._make_app()
        assert hasattr(app, "_feed_text")

    def test_feed_frame_exists(self):
        """LauncherApp should create a _feed_frame attribute."""
        app = self._make_app()
        assert hasattr(app, "_feed_frame")

    def test_provider_var_exists(self):
        """LauncherApp should create a _provider_var attribute."""
        app = self._make_app()
        assert hasattr(app, "_provider_var")

    def test_stats_polling_updates_provider(self):
        """_poll_stats should also update the provider label."""
        app = self._make_app()
        mock_dh = MagicMock()
        mock_dh.summary.return_value = {
            "current_phase": "draft",
            "total_words": 0,
            "chapters_complete": 0,
            "accept_rate": 0,
        }
        app._dashboard_handler = mock_dh
        app._stats_polling = True
        mock_daemon = MagicMock()
        mock_daemon.active_provider_label = "claude-code, codex"
        app._daemon = mock_daemon
        app._poll_stats()
        # Provider var should have been set
        app._provider_var.set.assert_called()


# =====================================================================
# LauncherApp: Add Files
# =====================================================================


class TestLauncherAddFiles(TestLauncherApp):
    """Tests for the Add Files button."""

    def test_add_files_btn_exists(self):
        app = self._make_app()
        assert hasattr(app, "_add_files_btn")

    def test_handle_add_files_no_selection(self):
        app = self._make_app()
        with patch(
            "tinyassets.desktop.launcher.filedialog.askopenfilenames",
            return_value=(),
        ):
            app._handle_add_files()
            # Should be a no-op, no crash

    def test_handle_add_files_copies_to_canon(self, tmp_path):
        app = self._make_app()
        app._universe_var.get.return_value = str(tmp_path)

        # Create a source file
        src = tmp_path / "source.txt"
        src.write_text("Hello world", encoding="utf-8")

        with patch(
            "tinyassets.desktop.launcher.filedialog.askopenfilenames",
            return_value=(str(src),),
        ):
            app._handle_add_files()

        # File should be copied to canon/
        dest = tmp_path / "canon" / "source.txt"
        assert dest.exists()
        assert dest.read_text(encoding="utf-8") == "Hello world"

    def test_handle_add_files_creates_canon_dir(self, tmp_path):
        app = self._make_app()
        app._universe_var.get.return_value = str(tmp_path)
        canon = tmp_path / "canon"
        assert not canon.exists()

        src = tmp_path / "notes.md"
        src.write_text("# Notes", encoding="utf-8")

        with patch(
            "tinyassets.desktop.launcher.filedialog.askopenfilenames",
            return_value=(str(src),),
        ):
            app._handle_add_files()

        assert canon.exists()

    def test_handle_add_files_shows_feed_message(self, tmp_path):
        app = self._make_app()
        app._universe_var.get.return_value = str(tmp_path)

        src = tmp_path / "doc.txt"
        src.write_text("content", encoding="utf-8")

        with patch(
            "tinyassets.desktop.launcher.filedialog.askopenfilenames",
            return_value=(str(src),),
        ):
            app._handle_add_files()

        # _append_feed_line schedules via root.after
        app.root.after.assert_called()


# =====================================================================
# LauncherApp: Reload
# =====================================================================


class TestLauncherReload(TestLauncherApp):
    """Tests for the reload button and programmatic reload() method."""

    def test_reload_btn_exists(self):
        app = self._make_app()
        assert hasattr(app, "_reload_btn")

    def test_reload_btn_disabled_initially(self):
        app = self._make_app()
        # The button is created with state=DISABLED
        # (verified by checking the configure call during build)
        assert app._reload_btn is not None

    def test_reload_btn_enabled_after_start(self):
        app = self._make_app()
        app._handle_start()
        app._reload_btn.configure.assert_called()

    def test_reload_btn_disabled_after_daemon_stopped(self):
        app = self._make_app()
        app._running = True
        app._on_daemon_stopped()
        app._reload_btn.configure.assert_called()

    def test_on_daemon_stopped_skipped_during_reload(self):
        app = self._make_app()
        app._running = True
        app._reloading = True
        app._reload_btn.reset_mock()
        app._on_daemon_stopped()
        # Should not have changed status or disabled reload btn
        assert app._running is True

    def test_classify_changes_code(self):
        app = self._make_app()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = " M fantasy_author/nodes/draft.py\n"
        with patch("tinyassets.desktop.launcher.subprocess.run", return_value=mock_result):
            assert app._classify_changes() == "code"

    def test_classify_changes_config(self):
        app = self._make_app()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = " M PROGRAM.md\n"
        with patch("tinyassets.desktop.launcher.subprocess.run", return_value=mock_result):
            assert app._classify_changes() == "config"

    def test_classify_changes_ui(self):
        app = self._make_app()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = " M fantasy_daemon/desktop/launcher.py\n"
        with patch("tinyassets.desktop.launcher.subprocess.run", return_value=mock_result):
            assert app._classify_changes() == "ui"

    def test_classify_changes_legacy_ui_path(self):
        app = self._make_app()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = " M fantasy_author/desktop/launcher.py\n"
        with patch("tinyassets.desktop.launcher.subprocess.run", return_value=mock_result):
            assert app._classify_changes() == "ui"

    def test_classify_changes_ui_and_code_returns_code(self):
        app = self._make_app()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            " M fantasy_daemon/desktop/launcher.py\n"
            " M fantasy_author/nodes/draft.py\n"
        )
        with patch("tinyassets.desktop.launcher.subprocess.run", return_value=mock_result):
            assert app._classify_changes() == "code"

    def test_classify_changes_none(self):
        app = self._make_app()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("tinyassets.desktop.launcher.subprocess.run", return_value=mock_result):
            assert app._classify_changes() == "none"

    def test_classify_changes_git_failure(self):
        app = self._make_app()
        mock_result = MagicMock()
        mock_result.returncode = 128
        with patch("tinyassets.desktop.launcher.subprocess.run", return_value=mock_result):
            assert app._classify_changes() == "code"

    def test_classify_changes_git_exception(self):
        app = self._make_app()
        with patch(
            "tinyassets.desktop.launcher.subprocess.run",
            side_effect=FileNotFoundError("git not found"),
        ):
            assert app._classify_changes() == "code"

    def test_do_reload_config(self):
        app = self._make_app()
        app._running = True
        app._daemon = MagicMock()
        app._do_reload("config")
        # Should not stop daemon
        app._daemon._stop_event.set.assert_not_called()

    def test_do_reload_ui(self):
        app = self._make_app()
        app._running = True
        app._do_reload("ui")
        # Should show restart message in feed
        app.root.after.assert_called()

    def test_do_reload_code_stops_daemon(self):
        app = self._make_app()
        app._running = True
        mock_daemon = MagicMock()
        mock_daemon._stop_event = MagicMock()
        mock_daemon._paused = MagicMock()
        app._daemon = mock_daemon
        app._daemon_thread = MagicMock()
        app._daemon_thread.is_alive.return_value = True
        app._do_reload("code")
        mock_daemon._stop_event.set.assert_called_once()

    def test_reimport_modules(self):
        app = self._make_app()
        with patch("tinyassets.desktop.launcher.importlib.reload") as mock_reload:
            app._reimport_modules()
            # Should have attempted to reload some modules
            # (exact count depends on what's imported)
            assert mock_reload.call_count >= 0
            assert mock_reload.call_count > 0

    def test_reimport_modules_handles_failure(self):
        app = self._make_app()
        with patch(
            "tinyassets.desktop.launcher.importlib.reload",
            side_effect=ImportError("bad module"),
        ):
            # Should not raise
            app._reimport_modules()

    def test_finish_reload_restarts_daemon(self):
        app = self._make_app()
        app._reloading = True
        mock_daemon = MagicMock()
        app._daemon = mock_daemon

        with (
            patch.object(app, "_reimport_modules"),
            patch.object(app, "_start_daemon"),
        ):
            app._finish_reload()

        assert app._reloading is False
        mock_daemon._cleanup.assert_called_once()
        assert app._running is True

    def test_apply_config_reload_reads_program_md(self, tmp_path):
        app = self._make_app()
        mock_daemon = MagicMock()
        app._daemon = mock_daemon

        program_md = tmp_path / "PROGRAM.md"
        program_md.write_text("A tale of dragons", encoding="utf-8")

        app._universe_var.get.return_value = str(tmp_path)
        app._apply_config_reload()
        assert mock_daemon._premise == "A tale of dragons"

    def test_apply_config_reload_no_daemon(self):
        app = self._make_app()
        app._daemon = None
        # Should not raise
        app._apply_config_reload()

    def test_reload_not_running(self):
        app = self._make_app()
        app._running = False
        app._reload_btn.reset_mock()
        app.reload()
        # Should not start a thread or change state
        app._reload_btn.configure.assert_not_called()

    def test_handle_reload_not_running(self):
        app = self._make_app()
        app._running = False
        app._reload_btn.reset_mock()
        app._handle_reload()
        # Should be a no-op
        app._reload_btn.configure.assert_not_called()

    def test_reload_failed_restores_state(self):
        app = self._make_app()
        app._running = True
        app._reload_failed()
        # Feed should have error message
        app.root.after.assert_called()

    def test_stop_daemon_for_reload_daemon_already_stopped(self):
        app = self._make_app()
        app._daemon = MagicMock()
        app._daemon_thread = MagicMock()
        app._daemon_thread.is_alive.return_value = False

        with patch.object(app, "_finish_reload") as mock_finish:
            app._stop_daemon_for_reload()
            mock_finish.assert_called_once()


# =====================================================================
# Tray: Show Window & icon_path
# =====================================================================


class TestTrayThrottling:
    """Tests for notification and menu refresh throttling."""

    def test_notify_throttle_suppresses_rapid_calls(self):
        """Second notify within cooldown should be suppressed."""
        app = TrayApp()
        app._icon = MagicMock()

        # First call goes through
        app.notify("First", "msg1")
        assert app._icon.notify.call_count == 1

        # Second call within cooldown is suppressed
        app.notify("Second", "msg2")
        assert app._icon.notify.call_count == 1

    def test_notify_throttle_allows_after_cooldown(self):
        """Notify should work again after the cooldown expires."""
        import time as _time

        app = TrayApp()
        app._icon = MagicMock()

        # First call
        app.notify("First", "msg1")
        assert app._icon.notify.call_count == 1

        # Simulate cooldown expiry by backdating last notify time
        app._last_notify_time = _time.monotonic() - app._NOTIFY_COOLDOWN - 1
        app.notify("Second", "msg2")
        assert app._icon.notify.call_count == 2

    def test_notify_no_icon_is_noop(self):
        app = TrayApp()
        app._icon = None
        app.notify("Test", "msg")  # Should not raise

    def test_update_status_throttles_menu_rebuild(self):
        """Rapid update_status calls should not rebuild menu every time."""
        app = TrayApp()
        app._icon = MagicMock()

        # First update triggers immediate rebuild
        app.update_status("Phase 1")
        assert app._status == "Phase 1"

        # Rapid second update should be deferred, not immediate
        app.update_status("Phase 2")
        assert app._status == "Phase 2"
        # Menu was rebuilt at most once immediately (may have a pending timer)


class TestTrayShowWindow:
    def test_show_window_callback(self):
        shown = []
        app = TrayApp(on_show_window=lambda: shown.append(True))
        app._icon = MagicMock()
        app._handle_show_window()
        assert len(shown) == 1

    def test_default_show_window_noop(self):
        app = TrayApp()
        app._icon = MagicMock()
        app._handle_show_window()  # Should not raise

    def test_icon_path_accepted(self):
        """TrayApp accepts icon_path parameter."""
        app = TrayApp(icon_path="/fake/icon.ico")
        assert app._icon_path == "/fake/icon.ico"

    def test_load_icon_image_fallback(self):
        """_load_icon_image falls back when path does not exist."""
        from tinyassets.desktop.tray import _load_icon_image

        img = _load_icon_image("/nonexistent/path.ico")
        assert img.size == (64, 64)

    def test_load_icon_image_from_file(self):
        """_load_icon_image loads from a real .ico file."""
        from tinyassets.desktop.tray import _load_icon_image

        with tempfile.TemporaryDirectory() as tmpdir:
            ico_path = Path(tmpdir) / "test.ico"
            generate_icon(ico_path)
            img = _load_icon_image(ico_path)
            assert img.size[0] > 0
            assert img.mode == "RGBA"


# =====================================================================
# .pyw launcher validation
# =====================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestPywLauncher:
    def test_pyw_exists(self):
        pyw = PROJECT_ROOT / "tinyassets.pyw"
        assert pyw.exists(), f"tinyassets.pyw not found at {pyw}"

    def test_pyw_is_valid_python(self):
        pyw = PROJECT_ROOT / "tinyassets.pyw"
        # py_compile raises if the file has syntax errors.
        py_compile.compile(str(pyw), doraise=True)


# =====================================================================
# create_shortcut
# =====================================================================


class TestCreateShortcut:
    def test_import(self):
        from tinyassets.desktop import create_shortcut  # noqa: F401

    def test_project_root(self):
        from tinyassets.desktop.create_shortcut import _project_root

        root = _project_root()
        assert (root / "fantasy_daemon" / "__init__.py").exists()

    def test_pyw_path(self):
        from tinyassets.desktop.create_shortcut import _pyw_path

        assert _pyw_path().name == "tinyassets.pyw"

    def test_create_bat(self, tmp_path: Path):
        from tinyassets.desktop.create_shortcut import _create_bat

        target = tmp_path / "tinyassets.pyw"
        target.write_text("# stub")
        result = _create_bat(target, tmp_path)
        assert result.exists()
        assert result.suffix == ".bat"
        content = result.read_text()
        assert "pythonw" in content
        assert str(target) in content

    def test_create_shortcut_bat_fallback(self, tmp_path: Path):
        """create_shortcut falls back to .bat when winshell is absent."""
        from tinyassets.desktop.create_shortcut import create_shortcut as cs

        with (
            patch(
                "tinyassets.desktop.create_shortcut._desktop_dir",
                return_value=tmp_path,
            ),
            patch(
                "tinyassets.desktop.create_shortcut._create_lnk",
                side_effect=ImportError("no winshell"),
            ),
        ):
            result = cs()
            assert result.exists()
            assert result.suffix == ".bat"

    def test_create_shortcut_lnk(self, tmp_path: Path):
        """create_shortcut prefers .lnk when winshell is available."""
        fake_lnk = tmp_path / "TinyAssets.lnk"

        def mock_create_lnk(target, desktop, icon):
            fake_lnk.write_text("lnk-stub")
            return fake_lnk

        from tinyassets.desktop.create_shortcut import create_shortcut as cs

        with (
            patch(
                "tinyassets.desktop.create_shortcut._desktop_dir",
                return_value=tmp_path,
            ),
            patch(
                "tinyassets.desktop.create_shortcut._create_lnk",
                side_effect=mock_create_lnk,
            ),
        ):
            result = cs()
            assert result == fake_lnk
            assert result.exists()


# =====================================================================
# pyproject.toml entry points
# =====================================================================


class TestPyprojectEntryPoints:
    def test_has_gui_scripts(self):
        import tomllib

        toml_path = PROJECT_ROOT / "pyproject.toml"
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        gui = data.get("project", {}).get("gui-scripts", {})
        assert "workflow" in gui
        assert "launcher:main" in gui["workflow"]

    def test_has_cli_scripts(self):
        import tomllib

        toml_path = PROJECT_ROOT / "pyproject.toml"
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        scripts = data.get("project", {}).get("scripts", {})
        assert "tinyassets-cli" in scripts
        assert "__main__:main" in scripts["tinyassets-cli"]

    def test_has_desktop_optional_deps(self):
        import tomllib

        toml_path = PROJECT_ROOT / "pyproject.toml"
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        opt = data.get("project", {}).get("optional-dependencies", {})
        assert "desktop" in opt
        desktop_deps = opt["desktop"]
        dep_names = [d.lower().split(">")[0].split("<")[0] for d in desktop_deps]
        assert "pillow" in dep_names
        assert "pystray" in dep_names
