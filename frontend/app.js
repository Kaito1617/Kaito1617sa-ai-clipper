/**
 * app.js — Frontend AI Clipper
 * Gestion drag & drop, WebSocket, progression, affichage des résultats.
 */

// ─────────────────────────────────────────────
// État de l'application
// ─────────────────────────────────────────────

const state = {
  fichierSelectionne: null,
  modeActif: 'football',
  dureeActive: 45,
  intensiteActive: 'normal',
  formatActif: 'portrait',
  nbShorts: 5,
  taskId: null,
  ws: null,
};

// ─────────────────────────────────────────────
// Références DOM
// ─────────────────────────────────────────────

const dropZone        = document.getElementById('drop-zone');
const fileInput       = document.getElementById('file-input');
const filePreview     = document.getElementById('file-preview');
const fileName        = document.getElementById('file-name');
const fileSize        = document.getElementById('file-size');
const btnRemove       = document.getElementById('btn-remove');
const btnGenerate     = document.getElementById('btn-generate');
const generateHint    = document.querySelector('.generate-hint');
const nbShortsSlider  = document.getElementById('nb-shorts');
const nbShortsVal     = document.getElementById('nb-shorts-val');
const progressSection = document.getElementById('progress-section');
const progressBar     = document.getElementById('progress-bar');
const progressPct     = document.getElementById('progress-pct');
const currentLabel    = document.getElementById('current-step-label');
const resultsSection  = document.getElementById('results-section');
const shortsGrid      = document.getElementById('shorts-grid');
const btnDownloadAll  = document.getElementById('btn-download-all');
const errorSection    = document.getElementById('error-section');
const errorMsg        = document.getElementById('error-msg');
const uploadSection   = document.getElementById('upload-section');

// ─────────────────────────────────────────────
// Drag & Drop
// ─────────────────────────────────────────────

dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', () => {
  dropZone.classList.remove('drag-over');
});

dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const fichier = e.dataTransfer.files[0];
  if (fichier) selectionnerFichier(fichier);
});

dropZone.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) selectionnerFichier(fileInput.files[0]);
});

function selectionnerFichier(fichier) {
  // Vérification type vidéo
  const extsAcceptees = ['mp4', 'avi', 'mkv', 'mov', 'webm', 'flv', 'ts'];
  const ext = fichier.name.split('.').pop().toLowerCase();
  if (!extsAcceptees.includes(ext)) {
    afficherNotification(`Format non supporté : .${ext}`, 'error');
    return;
  }

  state.fichierSelectionne = fichier;

  // Affichage aperçu
  fileName.textContent = fichier.name;
  fileSize.textContent = formaterTaille(fichier.size);
  filePreview.classList.remove('hidden');
  dropZone.style.opacity = '0.5';
  dropZone.style.pointerEvents = 'none';

  // Activation du bouton
  btnGenerate.disabled = false;
  generateHint.textContent = `${fichier.name} · Prêt à traiter`;
}

btnRemove.addEventListener('click', () => {
  state.fichierSelectionne = null;
  fileInput.value = '';
  filePreview.classList.add('hidden');
  dropZone.style.opacity = '';
  dropZone.style.pointerEvents = '';
  btnGenerate.disabled = true;
  generateHint.textContent = 'Sélectionne une vidéo pour commencer';
});

// ─────────────────────────────────────────────
// Sélection du mode
// ─────────────────────────────────────────────

document.querySelectorAll('.mode-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.modeActif = btn.dataset.mode;
  });
});

// ─────────────────────────────────────────────
// Paramètres
// ─────────────────────────────────────────────

nbShortsSlider.addEventListener('input', () => {
  state.nbShorts = parseInt(nbShortsSlider.value);
  nbShortsVal.textContent = state.nbShorts;
});

document.querySelectorAll('[data-duration]').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('[data-duration]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.dureeActive = parseInt(btn.dataset.duration);
  });
});

document.querySelectorAll('[data-intensity]').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('[data-intensity]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.intensiteActive = btn.dataset.intensity;
  });
});

document.querySelectorAll('[data-format]').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('[data-format]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.formatActif = btn.dataset.format;
  });
});

// ─────────────────────────────────────────────
// Génération — Upload + lancement pipeline
// ─────────────────────────────────────────────

btnGenerate.addEventListener('click', async () => {
  if (!state.fichierSelectionne) return;

  // Animation bouton
  btnGenerate.disabled = true;
  btnGenerate.classList.add('loading');
  btnGenerate.querySelector('.btn-label').textContent = 'Envoi en cours...';
  btnGenerate.querySelector('.btn-icon').textContent = '⏳';

  // Cacher sections résultats/erreurs précédentes
  resultsSection.classList.add('hidden');
  errorSection.classList.add('hidden');

  try {
    const formData = new FormData();
    formData.append('video', state.fichierSelectionne);
    formData.append('mode', state.modeActif);
    formData.append('nb_shorts', state.nbShorts);
    formData.append('duree_short', state.dureeActive);
    formData.append('intensite', state.intensiteActive);
    formData.append('format_sortie', state.formatActif);

    const reponse = await fetch('/api/upload', {
      method: 'POST',
      body: formData,
    });

    const donnees = await reponse.json();

    if (!reponse.ok) {
      throw new Error(donnees.erreur || `Erreur ${reponse.status}`);
    }

    state.taskId = donnees.task_id;

    // Affichage progression
    progressSection.classList.remove('hidden');
    progressSection.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // Connexion WebSocket
    connecterWebSocket(state.taskId);

  } catch (err) {
    afficherErreur(err.message);
    resetBoutonGenerer();
  }
});

// ─────────────────────────────────────────────
// WebSocket — Suivi de la progression
// ─────────────────────────────────────────────

function connecterWebSocket(taskId) {
  const wsUrl = `ws://${window.location.host}/ws/progress/${taskId}`;
  state.ws = new WebSocket(wsUrl);

  state.ws.onopen = () => {
    console.log('WebSocket connecté');
    // Keep-alive toutes les 15 secondes
    state.wsKeepAlive = setInterval(() => {
      if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send('ping');
      }
    }, 15000);
  };

  state.ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      mettreAJourProgression(msg);
    } catch (e) {
      console.warn('Message WS invalide:', event.data);
    }
  };

  state.ws.onerror = (err) => {
    console.error('WebSocket erreur:', err);
    // Fallback polling si WS échoue
    demarrerPolling(taskId);
  };

  state.ws.onclose = () => {
    clearInterval(state.wsKeepAlive);
    console.log('WebSocket fermé');
  };
}

// Polling fallback si WebSocket non disponible
function demarrerPolling(taskId) {
  state.pollingInterval = setInterval(async () => {
    try {
      const rep = await fetch(`/api/status/${taskId}`);
      const donnees = await rep.json();
      mettreAJourProgression(donnees);

      if (donnees.statut === 'terminee' || donnees.statut === 'erreur') {
        clearInterval(state.pollingInterval);
      }
    } catch (e) {
      console.error('Polling erreur:', e);
    }
  }, 2000);
}

// ─────────────────────────────────────────────
// Mise à jour de l'interface pendant le traitement
// ─────────────────────────────────────────────

const ETAPES_PIPELINE = [
  { id: 'step-transcription', motsCles: ['transcri', 'whisper', 'parole'] },
  { id: 'step-analyse',       motsCles: ['analys', 'llm', 'scorer', 'ia'] },
  { id: 'step-decoupe',       motsCles: ['sélect', 'découpe', 'moment'] },
  { id: 'step-effets',        motsCles: ['effet', 'zoom', 'sous-titre', 'sound', 'génér'] },
  { id: 'step-export',        motsCles: ['export', 'zip', 'prêt', 'terminé'] },
];

function mettreAJourProgression(msg) {
  const pct = Math.min(100, Math.max(0, msg.pourcentage || 0));
  const etape = msg.etape || '';

  // Barre de progression
  progressBar.style.width = `${pct}%`;
  progressPct.textContent = `${pct}%`;
  currentLabel.textContent = etape;

  // Mise à jour des steps visuels
  const etapeIndex = detecterEtapeActive(etape, pct);
  ETAPES_PIPELINE.forEach((step, i) => {
    const el = document.getElementById(step.id);
    if (!el) return;
    el.classList.remove('active', 'done');
    if (i < etapeIndex) {
      el.classList.add('done');
      el.querySelector('.step-status').textContent = '✓';
    } else if (i === etapeIndex) {
      el.classList.add('active');
      el.querySelector('.step-status').textContent = '⏳';
    }
  });

  // Terminé !
  if (msg.statut === 'terminee' && msg.shorts && msg.shorts.length > 0) {
    afficherResultats(msg);
  }

  // Erreur
  if (msg.statut === 'erreur') {
    afficherErreur(msg.erreur || 'Erreur inconnue');
  }
}

function detecterEtapeActive(etape, pct) {
  const etapeLower = etape.toLowerCase();
  for (let i = ETAPES_PIPELINE.length - 1; i >= 0; i--) {
    if (ETAPES_PIPELINE[i].motsCles.some(m => etapeLower.includes(m))) {
      return i;
    }
  }
  // Fallback basé sur le pourcentage
  if (pct < 20) return 0;
  if (pct < 42) return 1;
  if (pct < 47) return 2;
  if (pct < 95) return 3;
  return 4;
}

// ─────────────────────────────────────────────
// Affichage des résultats
// ─────────────────────────────────────────────

function afficherResultats(msg) {
  progressSection.classList.add('hidden');
  resultsSection.classList.remove('hidden');
  resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

  // Tous télécharger — URL construite côté client à partir du taskId connu
  const urlZip = `/api/download/${encodeURIComponent(state.taskId)}`;
  btnDownloadAll.onclick = () => { window.location.assign(urlZip); };
  btnDownloadAll.style.display = '';

  // Vider la grille
  shortsGrid.innerHTML = '';

  // Créer une card par short
  (msg.shorts || []).forEach((short) => {
    const card = creerCarteShort(short);
    shortsGrid.appendChild(card);
  });

  resetBoutonGenerer();
}

function creerCarteShort(short) {
  const div = document.createElement('div');
  div.className = 'short-card';

  const modeEmoji = { football: '⚽', anime: '🎌', streamer: '🎮' };
  const emoji = modeEmoji[state.modeActif] || '🎬';

  // Construire l'URL à partir de données connues côté client (pas WebSocket)
  // short.numero est un entier retourné par le serveur, on le valide
  const num = parseInt(short.numero, 10);
  if (!num || num < 1 || num > 20) return div;

  const modesSurs = ['football', 'anime', 'streamer'];
  const modeActifSur = modesSurs.includes(state.modeActif) ? state.modeActif : 'football';
  const nomFichierSur = `${modeActifSur}_short_${num}.mp4`;
  const urlVideo = `/api/shorts/${encodeURIComponent(state.taskId)}/${nomFichierSur}`;

  // Utilisation du DOM API pour éviter le XSS
  const videoWrap = document.createElement('div');
  videoWrap.className = 'short-video-wrap';

  const video = document.createElement('video');
  video.className = 'short-video';
  video.src = urlVideo;
  video.controls = true;
  video.preload = 'metadata';
  video.playsInline = true;
  videoWrap.appendChild(video);

  const badge = document.createElement('div');
  badge.className = 'short-badge';
  badge.textContent = `${emoji} Short #${num}`;
  videoWrap.appendChild(badge);

  const score = document.createElement('div');
  score.className = 'short-score';
  const scoreVal = parseFloat(short.score) || 0;
  score.textContent = `⭐ ${scoreVal}/100`;
  videoWrap.appendChild(score);

  const info = document.createElement('div');
  info.className = 'short-info';

  const meta = document.createElement('div');
  meta.className = 'short-meta';

  const titre = document.createElement('span');
  titre.className = 'short-title';
  titre.textContent = `Short #${num}`;
  meta.appendChild(titre);

  const duree = parseFloat(short.duree) || 0;
  const taille = parseFloat(short.taille_mo) || 0;
  const details = document.createElement('span');
  details.className = 'short-details';
  details.textContent = `${duree}s · ${taille} Mo`;
  meta.appendChild(details);

  info.appendChild(meta);

  const lienDl = document.createElement('a');
  lienDl.className = 'btn-dl';
  lienDl.href = urlVideo;
  lienDl.download = nomFichierSur;
  lienDl.textContent = '⬇ DL';
  info.appendChild(lienDl);

  div.appendChild(videoWrap);
  div.appendChild(info);

  return div;
}

// ─────────────────────────────────────────────
// Gestion erreurs
// ─────────────────────────────────────────────

function afficherErreur(message) {
  progressSection.classList.add('hidden');
  errorSection.classList.remove('hidden');
  errorMsg.textContent = message;
  errorSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
  resetBoutonGenerer();
}

document.getElementById('btn-retry').addEventListener('click', () => {
  errorSection.classList.add('hidden');
});

// ─────────────────────────────────────────────
// Reset
// ─────────────────────────────────────────────

function resetBoutonGenerer() {
  btnGenerate.classList.remove('loading');
  btnGenerate.querySelector('.btn-label').textContent = 'Générer les Shorts';
  btnGenerate.querySelector('.btn-icon').textContent = '✨';
  btnGenerate.disabled = !state.fichierSelectionne;
}

[document.getElementById('btn-restart'), document.getElementById('btn-retry')].forEach((btn) => {
  if (btn) {
    btn.addEventListener('click', () => {
      resultsSection.classList.add('hidden');
      errorSection.classList.add('hidden');
      progressSection.classList.add('hidden');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }
});

// ─────────────────────────────────────────────
// Utilitaires
// ─────────────────────────────────────────────

function formaterTaille(octets) {
  if (octets < 1024) return `${octets} o`;
  if (octets < 1024 * 1024) return `${(octets / 1024).toFixed(1)} Ko`;
  if (octets < 1024 * 1024 * 1024) return `${(octets / 1024 / 1024).toFixed(1)} Mo`;
  return `${(octets / 1024 / 1024 / 1024).toFixed(2)} Go`;
}

function afficherNotification(message, type = 'info') {
  const notif = document.createElement('div');
  const couleurs = {
    error: 'rgba(239,68,68,0.9)',
    success: 'rgba(16,185,129,0.9)',
    info: 'rgba(59,130,246,0.9)'
  };
  Object.assign(notif.style, {
    position: 'fixed',
    bottom: '24px',
    right: '24px',
    background: couleurs[type] || couleurs.info,
    color: 'white',
    padding: '12px 20px',
    borderRadius: '10px',
    fontWeight: '600',
    fontSize: '0.9rem',
    zIndex: '9999',
    backdropFilter: 'blur(8px)',
    animation: 'fadeInUp 0.3s ease',
    maxWidth: '320px',
  });
  notif.textContent = message;
  document.body.appendChild(notif);
  setTimeout(() => notif.remove(), 4000);
}

// ─────────────────────────────────────────────
// Animation CSS dynamique
// ─────────────────────────────────────────────

const style = document.createElement('style');
style.textContent = `
  @keyframes fadeInUp {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
  }
`;
document.head.appendChild(style);

console.log('%c🎬 AI Clipper chargé !', 'color: #8b5cf6; font-weight: bold; font-size: 14px;');
