from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView

from app.equalizer_widget import EqualizerWidget
from app.music_config import ensure_music_widget_defaults, enabled_providers, find_provider, first_enabled_provider, provider_paths
from app.logger import get_logger
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


class MusicWidget(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setObjectName("MusicWidget")
        self.config = config
        self.settings = ensure_music_widget_defaults(config)
        self.logger = get_logger()
        self.profiles = {}
        self.current_provider = None
        self.visualizer_failures = 0
        self.setVisible(bool(self.settings.get("visible", True)))
        self.setFixedWidth(int(self.settings.get("width", 420)))
        root = QVBoxLayout(self); root.setContentsMargins(6, 4, 6, 6); root.setSpacing(3)
        header = QHBoxLayout(); header.setSpacing(4)
        header.addWidget(QLabel("♪ Музыка"))
        self.provider_combo = QComboBox(); self.provider_combo.setObjectName("MusicProviderCombo")
        for p in enabled_providers(self.settings):
            self.provider_combo.addItem(p.get("name", p.get("id")), p.get("id"))
        self.provider_combo.currentIndexChanged.connect(self.on_provider_changed)
        header.addWidget(self.provider_combo, 1)
        self.reload_button = QPushButton("⟳"); self.reload_button.clicked.connect(self.reload)
        self.external_button = QPushButton("↗"); self.external_button.setToolTip("Открыть во внешнем браузере"); self.external_button.clicked.connect(self.open_external)
        self.clear_button = QPushButton("Очистить"); self.clear_button.setToolTip("Очистить сессию текущего провайдера"); self.clear_button.clicked.connect(self.clear_session)
        self.collapse_button = QPushButton(); self.collapse_button.clicked.connect(self.toggle_collapsed)
        for b in (self.reload_button, self.external_button, self.clear_button, self.collapse_button): header.addWidget(b)
        root.addLayout(header)
        self.equalizer = EqualizerWidget(self.settings.get("visualizer_bar_count"), self.settings.get("visualizer_fps"), self.settings.get("visualizer_mode"))
        self.equalizer.setVisible(bool(self.settings.get("visualizer_enabled", True)))
        root.addWidget(self.equalizer)
        self.message = QLabel(); self.message.setWordWrap(True); root.addWidget(self.message)
        self.view = register_web_view(QWebEngineView()); self.view.setMinimumHeight(int(self.settings.get("height", 220))); root.addWidget(self.view, 1)
        self.visualizer_poll_timer = QTimer(self); self.visualizer_poll_timer.timeout.connect(self.poll_visualizer_data)
        idx = self.provider_combo.findData(self.settings.get("active_provider")); self.provider_combo.setCurrentIndex(max(0, idx))
        self.apply_collapsed(bool(self.settings.get("collapsed", False)))
        self.logger.info("Music widget initialized")
        self.load_current_provider()

    def _profile_for(self, provider):
        pid = provider.get("id")
        if pid in self.profiles: return self.profiles[pid]
        profile_dir, cache_dir = provider_paths(provider)
        profile_dir.mkdir(parents=True, exist_ok=True); cache_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info("Music profile path: %s", profile_dir); self.logger.info("Music cache path: %s", cache_dir)
        profile = QWebEngineProfile(f"oko_music_{pid}", self)
        profile.setPersistentStoragePath(str(profile_dir)); profile.setCachePath(str(cache_dir))
        profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        self.profiles[pid] = profile
        return profile

    def on_provider_changed(self, *_):
        pid = self.provider_combo.currentData()
        from app.config import save_config
        self.settings["active_provider"] = pid; save_config(self.config)
        self.logger.info("Music provider selected: %s", pid)
        self.load_current_provider()

    def load_current_provider(self):
        provider = find_provider(self.settings, self.provider_combo.currentData()) or first_enabled_provider(self.settings)
        if not provider: return
        self.current_provider = provider
        page = QWebEnginePage(self._profile_for(provider), self.view); self.view.setPage(page)
        self.view.loadFinished.connect(self.on_load_finished)
        url = provider.get("url", "")
        if not url:
            self.message.setText("Укажите URL своего плеера в настройках"); self.view.hide(); return
        self.message.clear(); self.view.show(); self.logger.info("Music page loading: provider=%s", provider.get("id")); self.view.load(QUrl(url))
        self.restart_visualizer()

    def on_load_finished(self, ok):
        pid = (self.current_provider or {}).get("id")
        self.logger.info("Music page loaded: provider=%s" if ok else "Music page load failed: provider=%s", pid)
        self.install_real_visualizer()

    def install_real_visualizer(self):
        mode = self.settings.get("visualizer_mode", "auto")
        self.logger.info("Music visualizer mode: %s", mode)
        if mode == "decorative": return
        self.logger.info("Music visualizer real install requested")
        self.view.page().runJavaScript(VISUALIZER_JS, lambda result: self.logger.info("Music visualizer real installed" if isinstance(result, dict) and result.get("ok") else "Music visualizer fallback to decorative: reason=install_failed"))

    def restart_visualizer(self):
        self.visualizer_failures = 0
        if self.settings.get("visualizer_enabled", True):
            self.equalizer.set_mode(self.settings.get("visualizer_mode", "auto")); self.equalizer.start(); self.visualizer_poll_timer.start(1000)

    def poll_visualizer_data(self):
        if not self.view.page() or self.settings.get("visualizer_mode") == "decorative": return
        self.view.page().runJavaScript("window.__okoMusicVisualizerData || null", self.handle_visualizer_data)

    def handle_visualizer_data(self, data):
        if isinstance(data, dict) and data.get("ok") and data.get("levels"):
            self.visualizer_failures = 0; self.equalizer.set_mode("real"); self.equalizer.set_levels(data.get("levels")); return
        reason = data.get("error") if isinstance(data, dict) else "no_data"
        self.visualizer_failures += 1
        if self.visualizer_failures == 4:
            self.logger.warning("Music visualizer fallback to decorative: reason=%s", reason or "unknown")
            if self.settings.get("visualizer_mode") == "auto": self.equalizer.set_mode("decorative")

    def reload(self):
        self.view.reload()

    def open_external(self):
        url = (self.current_provider or {}).get("url", "")
        if url: QDesktopServices.openUrl(QUrl(url))

    def clear_session(self):
        if QMessageBox.question(self, "Очистить сессию", "Очистить cookies/cache текущего музыкального провайдера?") != QMessageBox.Yes: return
        profile = self.profiles.get((self.current_provider or {}).get("id"))
        if profile:
            profile.cookieStore().deleteAllCookies(); profile.clearHttpCache()
            self.logger.info("Music session cleared: provider=%s", self.current_provider.get("id"))
        self.reload()

    def toggle_collapsed(self):
        from app.config import save_config
        self.apply_collapsed(not self.settings.get("collapsed", False)); save_config(self.config)

    def apply_collapsed(self, collapsed):
        self.settings["collapsed"] = bool(collapsed); self.view.setVisible(not collapsed); self.message.setVisible(not collapsed and bool(self.message.text()))
        self.collapse_button.setText("Развернуть" if collapsed else "Свернуть")
        self.logger.info("Music widget collapsed" if collapsed else "Music widget expanded")
