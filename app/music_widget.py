from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFontMetrics
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView

from app.equalizer_widget import EqualizerWidget
from app.logger import get_logger
from app.music_config import (
    enabled_providers,
    ensure_music_widget_defaults,
    find_provider,
    first_enabled_provider,
    provider_paths,
)
from app.webengine_lifecycle import register_web_view


VISUALIZER_JS = r"""
(function(){try{if(window.__okoMusicVisualizerInstalled){return {ok:true,already:true};}
window.__okoMusicVisualizerInstalled=true;window.__okoMusicVisualizerData={ok:false,levels:[],playing:false,error:"",mode:"init"};
function install(){try{const audio=document.querySelector("audio");if(!audio){window.__okoMusicVisualizerData.error="audio_not_found";return;}
const C=window.AudioContext||window.webkitAudioContext;if(!C){window.__okoMusicVisualizerData.error="audio_context_not_supported";return;}
const ctx=new C();const source=ctx.createMediaElementSource(audio);const analyser=ctx.createAnalyser();analyser.fftSize=128;source.connect(analyser);analyser.connect(ctx.destination);const data=new Uint8Array(analyser.frequencyBinCount);
function tick(){try{analyser.getByteFrequencyData(data);window.__okoMusicVisualizerData={ok:true,levels:Array.from(data).map(v=>v/255),playing:!audio.paused,error:"",mode:"real"};}catch(e){window.__okoMusicVisualizerData.error=String(e&&e.message||e);}requestAnimationFrame(tick);}tick();}
catch(e){window.__okoMusicVisualizerData.error=String(e&&e.message||e);}}setTimeout(install,1500);return {ok:true,installed:true};}catch(e){return {ok:false,error:String(e&&e.message||e)};}})();
"""

METADATA_JS = r"""
(function(){try{const audio=document.querySelector('audio');const meta=(navigator.mediaSession&&navigator.mediaSession.metadata)||null;
const artwork=(meta&&meta.artwork&&meta.artwork.length)?meta.artwork[meta.artwork.length-1].src:'';
let title=(meta&&meta.title)||'';let artist=(meta&&meta.artist)||'';let album=(meta&&meta.album)||'';
if(!title){const selectors=['.track__name','.d-track__name','.player-controls__track','.Root__now-playing-bar a','[data-testid="context-item-info-title"]'];for(const s of selectors){const el=document.querySelector(s);if(el&&el.textContent.trim()){title=el.textContent.trim();break;}}}
if(!artist){const selectors=['.track__artists','.d-track__artists','.player-controls__artists','[data-testid="context-item-info-artist"]'];for(const s of selectors){const el=document.querySelector(s);if(el&&el.textContent.trim()){artist=el.textContent.trim();break;}}}
if(!title && document.title){title=document.title.replace(/\s*[-—|].*$/,'').trim()||document.title;}
return {title:title||'',artist:artist||'',album:album||'',artwork:artwork||'',currentTime:audio?audio.currentTime:0,duration:audio?audio.duration:0,paused:audio?audio.paused:true,muted:audio?audio.muted:false,volume:audio?audio.volume:1,readyState:audio?audio.readyState:0,audioFound:!!audio,srcPresent:!!(audio&&(audio.currentSrc||audio.src)),mediaSessionMetadataPresent:!!meta};
}catch(e){return {error:String(e&&e.message||e),title:'',artist:'',album:'',artwork:'',currentTime:0,duration:0,paused:true,muted:false,volume:1,readyState:0,audioFound:false,srcPresent:false,mediaSessionMetadataPresent:false};}})();
"""

AUDIO_DIAGNOSTICS_JS = r"""
(function(){try{const audio=document.querySelector('audio');if(audio&&audio.muted){audio.muted=false;audio.volume=1;}
return {audioFound:!!audio,paused:audio?audio.paused:true,muted:audio?audio.muted:false,volume:audio?audio.volume:1,currentTime:audio?audio.currentTime:0,duration:audio?audio.duration:0,readyState:audio?audio.readyState:0,srcPresent:!!(audio&&(audio.currentSrc||audio.src)),mediaSessionMetadataPresent:!!(navigator.mediaSession&&navigator.mediaSession.metadata),unmuted:!!audio&&!audio.muted};
}catch(e){return {error:String(e&&e.message||e),audioFound:false};}})();
"""

PLAY_PAUSE_JS = r"""
(function(){try{const audio=document.querySelector('audio');if(!audio){return {ok:false,reason:'audio_not_found'};}if(audio.paused){const p=audio.play();if(p&&p.catch){p.catch(function(e){window.__okoMusicPlayPauseError=String(e&&e.message||e);});}return {ok:true,action:'play'};}audio.pause();return {ok:true,action:'pause'};}catch(e){return {ok:false,reason:String(e&&e.message||e)};}})();
"""


def _format_time(seconds):
    try:
        seconds = int(float(seconds))
    except (TypeError, ValueError, OverflowError):
        return "--:--"
    if seconds <= 0:
        return "--:--"
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class MusicWidget(QFrame):
    """Compact header mini-player with full WebEngine player in a right drawer."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setObjectName("MusicMiniPlayer")
        self.config = config
        self.settings = ensure_music_widget_defaults(config)
        self.logger = get_logger()
        self.profiles = {}
        self.current_provider = None
        self.visualizer_failures = 0
        self._last_title = ""
        self._last_artist = ""
        self._main_window = parent

        self.setVisible(bool(self.settings.get("visible", True)) and bool(self.settings.get("mini_player_enabled", True)))
        self.setFixedHeight(int(self.settings.get("mini_player_height", 48)))
        self.setMinimumWidth(320)
        self.setMaximumWidth(int(self.settings.get("mini_player_width", 680)))

        self._build_mini_player()
        self._build_drawer()
        self._select_initial_provider()
        self._start_timers()
        self.load_current_provider()
        self.logger.info("Music mini-player initialized")

    def _build_mini_player(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)
        self.icon_label = QLabel("♪")
        self.provider_label = QLabel("Музыка")
        self.provider_label.setObjectName("MusicProviderLabel")
        self.artwork_label = QLabel("▣")
        self.artwork_label.setObjectName("MusicArtwork")
        self.artwork_label.setFixedSize(32, 32)
        self.artwork_label.setAlignment(Qt.AlignCenter)
        self.artwork_label.setVisible(bool(self.settings.get("mini_player_show_artwork", True)))
        text_box = QWidget()
        text_layout = QVBoxLayout(text_box)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)
        self.track_label = QLabel("Музыка")
        self.track_label.setObjectName("MusicTrackLabel")
        self.artist_label = QLabel("--")
        self.artist_label.setObjectName("MusicArtistLabel")
        text_layout.addWidget(self.track_label)
        text_layout.addWidget(self.artist_label)
        self.time_label = QLabel("--:-- / --:--")
        self.progress = QProgressBar()
        self.progress.setObjectName("MusicProgress")
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(90)
        self.progress.setFixedHeight(5)
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setVisible(bool(self.settings.get("mini_player_show_progress", True)))
        self.compact_equalizer = EqualizerWidget(
            self.settings.get("visualizer_compact_bar_count", 14),
            self.settings.get("visualizer_fps", 24),
            self.settings.get("visualizer_mode", "auto"),
        )
        self.compact_equalizer.setFixedSize(86, 26)
        self.compact_equalizer.setVisible(bool(self.settings.get("mini_player_show_equalizer", True)))
        self.play_button = QPushButton("▶")
        self.play_button.setFixedSize(28, 28)
        self.play_button.clicked.connect(self.toggle_play_pause)
        self.external_button = QPushButton("↗")
        self.external_button.setFixedSize(28, 28)
        self.external_button.clicked.connect(self.open_external)
        self.drawer_button = QPushButton("⤢")
        self.drawer_button.setFixedSize(28, 28)
        self.drawer_button.clicked.connect(self.toggle_drawer)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.provider_label)
        layout.addWidget(self.artwork_label)
        layout.addWidget(text_box, 1)
        layout.addWidget(self.time_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.compact_equalizer)
        layout.addWidget(self.play_button)
        layout.addWidget(self.external_button)
        layout.addWidget(self.drawer_button)

    def _build_drawer(self):
        self.drawer = QDockWidget("Музыка", self._main_window)
        self.drawer.setObjectName("MusicDrawer")
        self.drawer.setAllowedAreas(Qt.RightDockWidgetArea)
        self.drawer.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.drawer.setMinimumWidth(360)
        self.drawer.setMaximumWidth(620)
        self.drawer.resize(int(self.settings.get("panel_width", 420)), self.drawer.height())
        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(8, 8, 8, 8)
        header = QHBoxLayout()
        header.addWidget(QLabel("♪ Музыка"))
        self.provider_combo = QComboBox()
        self.provider_combo.setObjectName("MusicProviderCombo")
        for p in enabled_providers(self.settings):
            self.provider_combo.addItem(p.get("name", p.get("id")), p.get("id"))
        self.provider_combo.currentIndexChanged.connect(self.on_provider_changed)
        header.addWidget(self.provider_combo, 1)
        self.reload_button = QPushButton("⟳")
        self.reload_button.clicked.connect(self.reload)
        self.clear_button = QPushButton("Очистить")
        self.clear_button.clicked.connect(self.clear_session)
        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.close_drawer)
        self.drawer_external_button = QPushButton("↗")
        self.drawer_external_button.clicked.connect(self.open_external)
        for button in (self.reload_button, self.drawer_external_button, self.clear_button, close_button):
            header.addWidget(button)
        root.addLayout(header)
        self.full_equalizer = EqualizerWidget(
            self.settings.get("visualizer_bar_count", 24),
            self.settings.get("visualizer_fps", 24),
            self.settings.get("visualizer_mode", "auto"),
        )
        self.full_equalizer.setMinimumHeight(44)
        root.addWidget(self.full_equalizer)
        self.message = QLabel()
        self.message.setWordWrap(True)
        root.addWidget(self.message)
        self.view = register_web_view(QWebEngineView())
        root.addWidget(self.view, 1)
        self.drawer.setWidget(container)
        if self._main_window is not None and hasattr(self._main_window, "addDockWidget"):
            self._main_window.addDockWidget(Qt.RightDockWidgetArea, self.drawer)
        self.drawer.visibilityChanged.connect(self.on_drawer_visibility_changed)
        self.drawer.setVisible(bool(self.settings.get("panel_open", False)) and not bool(self.settings.get("collapsed", True)))
        self.logger.info("Music drawer initialized")

    def _select_initial_provider(self):
        idx = self.provider_combo.findData(self.settings.get("active_provider"))
        self.provider_combo.setCurrentIndex(max(0, idx))

    def _start_timers(self):
        self.metadata_timer = QTimer(self)
        self.metadata_timer.timeout.connect(self.poll_metadata)
        self.metadata_timer.start(int(self.settings.get("metadata_poll_ms", 1000)))
        self.visualizer_poll_timer = QTimer(self)
        self.visualizer_poll_timer.timeout.connect(self.poll_visualizer_data)
        if self.settings.get("visualizer_enabled", True):
            self.visualizer_poll_timer.start(1000)
            self.compact_equalizer.start()
            self.full_equalizer.start()

    def _profile_for(self, provider):
        pid = provider.get("id")
        if pid in self.profiles:
            return self.profiles[pid]
        profile_dir, cache_dir = provider_paths(provider)
        profile_dir.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info("Music profile path: %s", profile_dir)
        self.logger.info("Music cache path: %s", cache_dir)
        profile = QWebEngineProfile(f"oko_music_{pid}", self)
        profile.setPersistentStoragePath(str(profile_dir))
        profile.setCachePath(str(cache_dir))
        profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        self.profiles[pid] = profile
        return profile

    def _provider_short_name(self, provider):
        pid = (provider or {}).get("id", "")
        if pid == "yandex_music":
            return "Ян"
        if pid == "spotify":
            return "Spotify"
        return "Custom"

    def on_provider_changed(self, *_):
        pid = self.provider_combo.currentData()
        from app.config import save_config
        self.settings["active_provider"] = pid
        save_config(self.config)
        self.logger.info("Music provider selected: %s", pid)
        self.load_current_provider()

    def load_current_provider(self):
        provider = find_provider(self.settings, self.provider_combo.currentData()) or first_enabled_provider(self.settings)
        if not provider:
            return
        self.current_provider = provider
        self.provider_label.setText(self._provider_short_name(provider))
        page = QWebEnginePage(self._profile_for(provider), self.view)
        if hasattr(page, "setAudioMuted"):
            page.setAudioMuted(False)
        self.view.setPage(page)
        self.view.loadFinished.connect(self.on_load_finished)
        url = provider.get("url", "")
        if not url:
            self.message.setText("Укажите URL своего плеера в настройках")
            self.view.hide()
            self.update_metadata({})
            return
        self.message.clear()
        self.view.show()
        self.logger.info("Music page loading: provider=%s", provider.get("id"))
        self.view.load(QUrl(url))
        self.restart_visualizer()

    def on_load_finished(self, ok):
        pid = (self.current_provider or {}).get("id")
        self.logger.info("Music page loaded: provider=%s" if ok else "Music page load failed: provider=%s", pid)
        if hasattr(self.view.page(), "setAudioMuted"):
            self.view.page().setAudioMuted(False)
        self.install_real_visualizer()
        self.run_audio_diagnostics()
        self.poll_metadata()

    def install_real_visualizer(self):
        mode = self.settings.get("visualizer_mode", "auto")
        self.logger.info("Music visualizer mode: %s", mode)
        if mode == "decorative" or not self.view.page():
            return
        self.logger.info("Music visualizer real install requested")
        self.view.page().runJavaScript(
            VISUALIZER_JS,
            lambda result: self.logger.info(
                "Music visualizer real installed"
                if isinstance(result, dict) and result.get("ok")
                else "Music visualizer fallback to decorative: reason=install_failed"
            ),
        )

    def restart_visualizer(self):
        self.visualizer_failures = 0
        for equalizer in (self.compact_equalizer, self.full_equalizer):
            equalizer.set_mode(self.settings.get("visualizer_mode", "auto"))
            equalizer.start()

    def poll_visualizer_data(self):
        if not self.view.page() or self.settings.get("visualizer_mode") == "decorative":
            return
        self.view.page().runJavaScript("window.__okoMusicVisualizerData || null", self.handle_visualizer_data)

    def handle_visualizer_data(self, data):
        if isinstance(data, dict) and data.get("ok") and data.get("levels"):
            self.visualizer_failures = 0
            levels = data.get("levels")
            for equalizer in (self.compact_equalizer, self.full_equalizer):
                equalizer.set_mode("real")
                equalizer.set_levels(levels)
            return
        reason = data.get("error") if isinstance(data, dict) else "no_data"
        self.visualizer_failures += 1
        if self.visualizer_failures == 4:
            self.logger.warning("Music visualizer fallback to decorative: reason=%s", reason or "unknown")
            if self.settings.get("visualizer_mode") == "auto":
                self.compact_equalizer.set_mode("decorative")
                self.full_equalizer.set_mode("decorative")

    def poll_metadata(self):
        if self.view.page():
            self.view.page().runJavaScript(METADATA_JS, self.update_metadata)

    def update_metadata(self, data):
        provider_name = (self.current_provider or {}).get("name") or "Музыка"
        if not isinstance(data, dict):
            data = {}
        title = (data.get("title") or "Музыка").strip()
        artist = (data.get("artist") or provider_name).strip()
        current = data.get("currentTime") or 0
        duration = data.get("duration") or 0
        paused = bool(data.get("paused", True))
        self._set_elided(self.track_label, title)
        self._set_elided(self.artist_label, artist)
        self.time_label.setText(f"{_format_time(current)} / {_format_time(duration)}")
        if duration and duration > 0:
            self.progress.setRange(0, 1000)
            self.progress.setValue(max(0, min(1000, int(float(current) / float(duration) * 1000))))
        else:
            self.progress.setValue(0)
        self.play_button.setText("▶" if paused else "⏸")
        if title != self._last_title or artist != self._last_artist:
            self.logger.info(
                "Music metadata updated: provider=%s, title_present=%s, artist_present=%s",
                (self.current_provider or {}).get("id"),
                bool(data.get("title")),
                bool(data.get("artist")),
            )
            self._last_title = title
            self._last_artist = artist

    def _set_elided(self, label, text):
        metrics = QFontMetrics(label.font())
        label.setText(metrics.elidedText(text or "", Qt.ElideRight, max(60, label.width() or 180)))
        label.setToolTip(text or "")

    def run_audio_diagnostics(self):
        if not self.view.page():
            return
        self.view.page().runJavaScript(AUDIO_DIAGNOSTICS_JS, self.handle_audio_diagnostics)

    def handle_audio_diagnostics(self, data):
        if not isinstance(data, dict):
            data = {"audioFound": False}
        self.logger.info(
            "Music audio diagnostics: provider=%s, audio_found=%s, paused=%s, muted=%s, ready_state=%s, src_present=%s, media_session=%s",
            (self.current_provider or {}).get("id"),
            data.get("audioFound"),
            data.get("paused"),
            data.get("muted"),
            data.get("readyState"),
            data.get("srcPresent"),
            data.get("mediaSessionMetadataPresent"),
        )
        if data.get("audioFound") and not data.get("muted"):
            self.logger.info("Music audio unmuted")

    def toggle_play_pause(self):
        self.logger.info("Music play/pause requested")
        if not self.view.page():
            return
        self.view.page().runJavaScript(PLAY_PAUSE_JS, self.handle_play_pause_result)

    def handle_play_pause_result(self, result):
        if not isinstance(result, dict) or not result.get("ok"):
            reason = result.get("reason") if isinstance(result, dict) else "unknown"
            self.logger.warning("Music play/pause failed: reason=%s", reason)
        self.poll_metadata()

    def reload(self):
        self.view.reload()

    def open_external(self):
        url = (self.current_provider or {}).get("url", "")
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def clear_session(self):
        if QMessageBox.question(self, "Очистить сессию", "Очистить cookies/cache текущего музыкального провайдера?") != QMessageBox.Yes:
            return
        profile = self.profiles.get((self.current_provider or {}).get("id"))
        if profile:
            profile.cookieStore().deleteAllCookies()
            profile.clearHttpCache()
            self.logger.info("Music session cleared: provider=%s", self.current_provider.get("id"))
        self.reload()

    def toggle_drawer(self):
        self.drawer.setVisible(not self.drawer.isVisible())

    def close_drawer(self):
        self.drawer.setVisible(False)

    def on_drawer_visibility_changed(self, visible):
        from app.config import save_config
        self.settings["panel_open"] = bool(visible)
        self.settings["collapsed"] = not bool(visible)
        self.drawer_button.setText("⤡" if visible else "⤢")
        save_config(self.config)
        self.logger.info("Music drawer opened" if visible else "Music drawer closed")
