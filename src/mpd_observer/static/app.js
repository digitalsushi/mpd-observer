const ui = Object.fromEntries(['app','artwork','artwork-backdrop','artwork-backdrop-image','album-backdrop','album-backdrop-text','title','artist','album','elapsed','duration','progress-row','progress-fill','estimated-progress','progress-pie','weather','temperature','clock','date'].map(id => [id.replace(/-/g,'_'), document.getElementById(id)]));
let snapshot = null;
let artworkKey = null;
let trackTextKey = null;
let trackTextColors = [];
let lastTrackTextColor = null;

const formatTime = seconds => {
  if (!Number.isFinite(seconds)) return '0:00';
  const value = Math.max(0, Math.floor(seconds));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
};

async function configure() {
  const settings = await fetch('/api/settings').then(response => response.json());
  document.title = settings.title;
  for (const [name, value] of Object.entries(settings.theme))
    document.documentElement.style.setProperty(`--${name === 'background' ? 'bg' : name === 'foreground' ? 'fg' : name}`, value);
  if (!settings.show_clock) document.querySelector('aside').style.display = 'none';
  trackTextColors = settings.track_text_colors || [];
  applyTrackTextColor();
  setInterval(refresh, settings.refresh_interval_ms);
}

function applyTrackTextColor() {
  const track = snapshot?.track;
  if (!track || !trackTextColors.length) return;
  const key = `${track.uri}\0${track.artist}\0${track.title}`;
  if (key === trackTextKey) return;
  trackTextKey = key;
  const choices = trackTextColors.filter(color => color !== lastTrackTextColor);
  lastTrackTextColor = choices[Math.floor(Math.random() * choices.length)] || trackTextColors[0];
  document.documentElement.style.setProperty('--track-text', lastTrackTextColor);
}

async function refresh() {
  try {
    snapshot = await fetch('/api/now-playing', {cache:'no-store'}).then(response => response.json());
    render();
  } catch (_) {
    snapshot = {connected:false, state:'offline', track:null};
    render();
  }
}

async function refreshWeather() {
  try {
    const weather = await fetch('/api/weather', {cache:'no-store'}).then(response => response.json());
    ui.weather.hidden = !weather.available;
    if (!weather.available) return;
    document.documentElement.classList.toggle('weather-alert', Boolean(weather.severe_weather_alert));
    ui.temperature.textContent = `${Math.round(weather.temperature_f)}°`;
    ui.weather.querySelector('svg').dataset.condition = weather.condition;
    ui.weather.classList.toggle('stale', Boolean(weather.stale));
    ui.weather.title = `${weather.condition}, ${Math.round(weather.temperature_f)}°F${weather.stale ? ' (stale)' : ''}`;
  } catch (_) {
    // Preserve the most recent reading if the local request briefly fails.
  }
}

function render() {
  const track = snapshot.track;
  ui.app.classList.toggle('offline', !snapshot.connected);
  ui.title.textContent = track?.title || 'MPD Observer';
  ui.title.classList.toggle('long', ui.title.textContent.length > 35);
  ui.title.classList.toggle('very-long', ui.title.textContent.length > 55);
  ui.artist.textContent = track ? (track.artist || '') : (snapshot.message || 'Waiting for the music…');
  ui.album.textContent = track?.album || '';
  applyTrackTextColor();
  updateArtworkLayout();
  const estimated = Boolean(snapshot.duration_estimated && snapshot.duration);
  ui.estimated_progress.hidden = !estimated;
  ui.progress_row.hidden = estimated || !snapshot.duration;
  const nextArtworkKey = track ? `${track.uri}\0${track.artist}\0${track.title}` : null;
  if (nextArtworkKey !== artworkKey) {
    artworkKey = nextArtworkKey;
    ui.artwork.classList.remove('error');
    ui.artwork.removeAttribute('src');
    if (track?.uri) ui.artwork.src = `/api/artwork?uri=${encodeURIComponent(track.uri)}&v=${Date.now()}`;
  }
}

function updateArtworkLayout() {
  const album = snapshot?.track?.album || '';
  const artist = snapshot?.track?.artist || '';
  const backgroundText = album || artist;
  const atmospheric = Boolean(backgroundText && ui.artwork.classList.contains('error'));
  ui.app.classList.toggle('album-atmosphere', atmospheric);
  ui.album_backdrop.classList.toggle('active', atmospheric);
  ui.album_backdrop_text.textContent = backgroundText;
  ui.album_backdrop_text.dataset.text = backgroundText;
}

ui.artwork.addEventListener('load', () => {
  ui.artwork.classList.remove('error');
  ui.artwork_backdrop_image.src = ui.artwork.currentSrc || ui.artwork.src;
  ui.artwork_backdrop.classList.add('active');
  updateArtworkLayout();
});
ui.artwork.addEventListener('error', () => {
  ui.artwork.classList.add('error');
  ui.artwork_backdrop.classList.remove('active');
  ui.artwork_backdrop_image.removeAttribute('src');
  updateArtworkLayout();
});
setInterval(() => {
  const now = new Date();
  ui.clock.textContent = now.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
  ui.date.textContent = now.toLocaleDateString([], {weekday:'long', month:'short', day:'numeric'});
  if (!snapshot) return;
  const advance = snapshot.state === 'play' ? Date.now()/1000 - snapshot.observed_at : 0;
  const elapsed = (snapshot.elapsed || 0) + advance;
  const estimated = Boolean(snapshot.duration_estimated && snapshot.duration);
  ui.estimated_progress.hidden = !estimated;
  ui.progress_row.hidden = estimated || !snapshot.duration;
  if (estimated) {
    const segment = Math.min(8, Math.floor(elapsed / snapshot.duration * 8));
    ui.progress_pie.style.setProperty('--fill', `${segment * 45}deg`);
    ui.estimated_progress.setAttribute('aria-label', `Estimated track progress: ${segment} of 8 segments`);
    ui.estimated_progress.title = `Estimated progress: ${segment}/8`;
  }
  ui.elapsed.textContent = formatTime(elapsed);
  ui.duration.textContent = formatTime(snapshot.duration);
  ui.progress_fill.style.width = snapshot.duration ? `${Math.min(100, elapsed / snapshot.duration * 100)}%` : '0';
}, 500);
configure().catch(() => {});
refresh();
refreshWeather();
setInterval(refreshWeather, 60000);
