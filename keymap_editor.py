#!/usr/bin/env python3
"""
okojyo_keyboard キーマップ Web エディター
Usage: python keymap_editor.py
Open: http://localhost:5001
"""

from flask import Flask, jsonify, request
import subprocess, re, os, sys, json, webbrowser, threading

app = Flask(__name__)
REPO = os.path.dirname(os.path.abspath(__file__))
KEYMAP_FILE = os.path.join(REPO, 'config', 'keymap.keymap')

LAYER_META = [
    {'name': 'L0 ベース',      'trigger': '常時アクティブ'},
    {'name': 'L1 シンボル',    'trigger': 'DEL長押し'},
    {'name': 'L2 ナビ/テンキー','trigger': 'SPC長押し'},
    {'name': 'L3 Fn/BT',       'trigger': 'ESC長押し or →L3'},
    {'name': 'L4 FPS',         'trigger': 'L3の →L4'},
]

# ── keymap parse / generate ──────────────────────────────────────────────────

def read_keymap():
    with open(KEYMAP_FILE, encoding='utf-8') as f:
        return f.read()

def parse_layers(content):
    """Return dict {layer_id: [binding, ...]}"""
    result = {}
    for m in re.finditer(r'layer_(\d+)\s*\{[^}]*?bindings\s*=\s*<(.*?)>;', content, re.DOTALL):
        idx = int(m.group(1))
        raw = m.group(2)
        # split on whitespace boundaries before &
        tokens = re.findall(r'&[^\n&]+', raw)
        bindings = [' '.join(t.split()) for t in tokens]
        result[idx] = bindings
    return result

def format_layer_block(bindings):
    """Format 44 bindings into the 12-12-12-8 keymap layout."""
    # 36 main keys: 3 rows of 12
    # 8 thumb keys
    rows_main = [bindings[0:12], bindings[12:24], bindings[24:36]]
    thumb     = bindings[36:44]

    def pad(b, w=28): return b.ljust(w)

    lines = ['\n']
    for row in rows_main:
        left  = '  '.join(pad(b) for b in row[:6])
        right = '  '.join(pad(b) for b in row[6:])
        lines.append(f'{left}  {right}')

    # thumb: left 5, right 3
    tl = '  '.join(pad(b, 26) for b in thumb[:5])
    tr = '  '.join(pad(b, 26) for b in thumb[5:])
    lines.append(f'           {tl}  {tr}')
    lines.append('            ')
    return '\n'.join(lines)

def update_keymap(layers_dict):
    """Rewrite layer bindings in the keymap file."""
    content = read_keymap()
    for layer_id, bindings in layers_dict.items():
        body = format_layer_block(bindings)
        pattern = re.compile(
            r'(layer_%d\s*\{[^}]*?bindings\s*=\s*<)(.*?)(>;)' % layer_id,
            re.DOTALL)
        content = pattern.sub(lambda m: m.group(1) + body + m.group(3), content)
    with open(KEYMAP_FILE, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)

# ── git helpers ───────────────────────────────────────────────────────────────

def git(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO, **kw)

def get_diff():
    r = git(['git', 'diff', 'config/keymap.keymap'])
    return r.stdout or '（変更なし）'

def git_push(message):
    git(['git', 'add', 'config/keymap.keymap'])
    r = git(['git', 'commit', '-m', message])
    if r.returncode != 0 and 'nothing to commit' not in r.stdout + r.stderr:
        return False, r.stderr
    r2 = git(['git', 'push', 'origin', 'HEAD'])
    return r2.returncode == 0, r2.stdout + r2.stderr

# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route('/api/layers')
def api_layers():
    content = read_keymap()
    layers = parse_layers(content)
    return jsonify({'layers': layers, 'meta': LAYER_META})

@app.route('/api/save', methods=['POST'])
def api_save():
    data = request.json
    layers = {int(k): v for k, v in data['layers'].items()}
    update_keymap(layers)
    return jsonify({'ok': True})

@app.route('/api/diff')
def api_diff():
    return jsonify({'diff': get_diff()})

@app.route('/api/push', methods=['POST'])
def api_push():
    msg = request.json.get('message', 'キーマップ更新（Webエディター）')
    ok, out = git_push(msg)
    return jsonify({'ok': ok, 'output': out})

@app.route('/')
def index():
    return HTML

# ── Embedded UI ───────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>Keymap Editor</title>
<style>
:root {
  --bg:#0d0f1a; --surface:#161929; --surface2:#1e2240;
  --border:#2a2e50; --text:#dde1f0; --muted:#5a607a; --accent:#5578f0;
}
* { box-sizing:border-box; margin:0; padding:0; }
body { background:var(--bg); color:var(--text); font:14px/1.5 system-ui,sans-serif; padding:24px; }

h1 { font-size:18px; letter-spacing:3px; color:var(--accent); margin-bottom:4px; }
.sub { font-size:11px; color:var(--muted); margin-bottom:24px; }

/* tabs */
.tabs { display:flex; gap:4px; border-bottom:1px solid var(--border); margin-bottom:20px; }
.tab { background:none; border:none; border-bottom:2px solid transparent;
       color:var(--muted); cursor:pointer; font:600 13px system-ui; padding:8px 18px 10px;
       margin-bottom:-1px; border-radius:6px 6px 0 0; }
.tab:hover { color:var(--text); background:var(--surface); }
.tab.active { color:var(--text); border-bottom-color:var(--accent); background:var(--surface2); }

/* keyboard grid */
.kb { background:var(--surface); border:1px solid var(--border); border-radius:14px;
      padding:20px 24px 18px; }
.kb-row { display:flex; gap:5px; margin-bottom:5px; }
.half { display:inline-flex; flex-direction:column; gap:5px; }
.gap { width:36px; display:inline-flex; align-items:center; justify-content:center;
       color:var(--border); font-size:20px; }

.key {
  width:52px; height:52px; border:1px solid var(--border); border-radius:7px;
  background:var(--surface2); display:flex; align-items:center; justify-content:center;
  cursor:pointer; font:700 11px ui-monospace,monospace; color:var(--text);
  text-align:center; padding:3px; line-height:1.2;
  box-shadow:0 2px 0 rgba(0,0,0,.4);
  transition:filter .1s;
}
.key:hover { filter:brightness(1.3); }
.key.empty { color:var(--muted); font-weight:400; font-size:9px; background:#0a0c18; border-color:#14162a; }
.key.modified { border-color:#5578f0; background:#1a2050; }

.thumb-row { display:flex; gap:5px; margin-top:10px; }
.tw { width:60px; }

/* toolbar */
.toolbar { display:flex; gap:10px; margin-top:18px; flex-wrap:wrap; align-items:center; }
.btn {
  padding:8px 18px; border-radius:7px; border:1px solid var(--border);
  background:var(--surface2); color:var(--text); cursor:pointer;
  font:600 13px system-ui; transition:filter .1s;
}
.btn:hover { filter:brightness(1.2); }
.btn-primary { background:#2a40a0; border-color:#4060d0; }
.btn-danger  { background:#8a1a1a; border-color:#c03030; }
.btn-green   { background:#1a5a2a; border-color:#30a050; }

/* modal */
.overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,.7);
           z-index:100; align-items:center; justify-content:center; }
.overlay.show { display:flex; }
.modal { background:var(--surface); border:1px solid var(--border); border-radius:14px;
         padding:24px; width:360px; }
.modal h2 { font-size:15px; margin-bottom:14px; }
.modal label { display:block; font-size:12px; color:var(--muted); margin-bottom:4px; }
.modal input, .modal select {
  width:100%; padding:8px 10px; background:var(--surface2); border:1px solid var(--border);
  border-radius:6px; color:var(--text); font:13px ui-monospace,monospace; margin-bottom:12px;
}
.modal input:focus, .modal select:focus { outline:none; border-color:var(--accent); }
.modal-buttons { display:flex; gap:8px; margin-top:4px; }

/* diff */
.diff-box {
  background:#0a0c18; border:1px solid var(--border); border-radius:8px;
  padding:14px; margin-top:14px; font:12px ui-monospace,monospace;
  white-space:pre; overflow-x:auto; max-height:300px; overflow-y:auto;
  display:none;
}
.diff-add { color:#50d080; }
.diff-del { color:#e05050; }
.diff-meta { color:var(--muted); }

/* status */
.status { margin-top:10px; font-size:12px; color:var(--muted); min-height:18px; }
.status.ok { color:#50d080; }
.status.err { color:#e05050; }

/* layer hint */
.layer-hint { font-size:11px; color:var(--muted); background:var(--surface2);
              border:1px solid var(--border); border-radius:4px;
              padding:2px 8px; display:inline-block; margin-bottom:14px; }
</style>
</head>
<body>
<h1>⌨ okojyo_keyboard Editor</h1>
<p class="sub">キーをクリックして編集 → Save → Diff確認 → Push</p>

<div class="tabs" id="tabs"></div>
<div id="kb-area"></div>

<div class="toolbar">
  <button class="btn btn-primary" onclick="saveToFile()">💾 Save to File</button>
  <button class="btn" onclick="showDiff()">📋 Diff を確認</button>
  <button class="btn btn-green" onclick="openPushModal()">🚀 Push to GitHub</button>
  <button class="btn" onclick="reloadFromFile()">↺ Reload</button>
</div>

<div class="diff-box" id="diff-box"></div>
<div class="status" id="status"></div>

<!-- Key Edit Modal -->
<div class="overlay" id="key-modal">
  <div class="modal">
    <h2 id="modal-title">キー編集</h2>
    <label>バインディング（ZMK記法）</label>
    <input type="text" id="binding-input" placeholder="例: &kp A, &mt LSHIFT TAB, &lt 1 ESC" />
    <label>クイック選択</label>
    <select id="binding-preset" onchange="applyPreset()">
      <option value="">— プリセット —</option>
      <optgroup label="通常キー">
        <option value="&trans">&amp;trans（透過）</option>
        <option value="&none">&amp;none（無効）</option>
      </optgroup>
      <optgroup label="モディファイア">
        <option value="&kp LEFT_CONTROL">&amp;kp LEFT_CONTROL</option>
        <option value="&kp LEFT_SHIFT">&amp;kp LEFT_SHIFT</option>
        <option value="&kp LEFT_ALT">&amp;kp LEFT_ALT</option>
        <option value="&kp LEFT_WIN">&amp;kp LEFT_WIN</option>
        <option value="&kp RIGHT_SHIFT">&amp;kp RIGHT_SHIFT</option>
        <option value="&kp RIGHT_ALT">&amp;kp RIGHT_ALT</option>
      </optgroup>
      <optgroup label="特殊キー">
        <option value="&kp ESC">&amp;kp ESC</option>
        <option value="&kp TAB">&amp;kp TAB</option>
        <option value="&kp SPACE">&amp;kp SPACE</option>
        <option value="&kp ENTER">&amp;kp ENTER</option>
        <option value="&kp BSPC">&amp;kp BSPC</option>
        <option value="&kp DELETE">&amp;kp DELETE</option>
      </optgroup>
      <optgroup label="レイヤー">
        <option value="&to 0">&amp;to 0</option>
        <option value="&to 1">&amp;to 1</option>
        <option value="&to 2">&amp;to 2</option>
        <option value="&to 3">&amp;to 3</option>
        <option value="&to 4">&amp;to 4</option>
      </optgroup>
      <optgroup label="マウス">
        <option value="&mkp LCLK">&amp;mkp LCLK（左クリック）</option>
        <option value="&mkp RCLK">&amp;mkp RCLK（右クリック）</option>
        <option value="&mkp MCLK">&amp;mkp MCLK（中クリック）</option>
        <option value="&msc SCRL_UP">&amp;msc SCRL_UP</option>
        <option value="&msc SCRL_DOWN">&amp;msc SCRL_DOWN</option>
      </optgroup>
      <optgroup label="Bluetooth">
        <option value="&bt BT_SEL 0">&amp;bt BT_SEL 0（PC1）</option>
        <option value="&bt BT_SEL 1">&amp;bt BT_SEL 1（PC2）</option>
        <option value="&bt BT_CLR">&amp;bt BT_CLR</option>
      </optgroup>
    </select>
    <div class="modal-buttons">
      <button class="btn btn-primary" onclick="applyEdit()">適用</button>
      <button class="btn" onclick="closeModal()">キャンセル</button>
    </div>
  </div>
</div>

<!-- Push Modal -->
<div class="overlay" id="push-modal">
  <div class="modal">
    <h2>🚀 Push to GitHub</h2>
    <label>コミットメッセージ</label>
    <input type="text" id="commit-msg" value="キーマップ更新（Webエディター）" />
    <div style="font-size:12px;color:var(--muted);margin-bottom:12px">
      ※ pushの前に必ずDiffを確認してください
    </div>
    <div class="modal-buttons">
      <button class="btn btn-green" onclick="doPush()">Push</button>
      <button class="btn" onclick="document.getElementById('push-modal').classList.remove('show')">キャンセル</button>
    </div>
    <div id="push-status" class="status"></div>
  </div>
</div>

<script>
// ── State ──
let layers = {};   // {0: [binding, ...], ...}
let meta = [];
let currentLayer = 0;
let editingKey = null;   // {layerId, keyIdx}
let originalLayers = {};

// ── Init ──
async function init() {
  const r = await fetch('/api/layers');
  const d = await r.json();
  layers = d.layers;
  meta = d.meta;
  originalLayers = JSON.parse(JSON.stringify(layers));
  buildTabs();
  renderLayer(0);
}

// ── Tabs ──
function buildTabs() {
  const el = document.getElementById('tabs');
  el.innerHTML = '';
  Object.keys(layers).forEach(id => {
    const m = meta[id] || {name: 'Layer ' + id, trigger: ''};
    const btn = document.createElement('button');
    btn.className = 'tab' + (id == 0 ? ' active' : '');
    btn.textContent = m.name;
    btn.title = m.trigger;
    btn.onclick = () => { currentLayer = parseInt(id); switchTab(btn, id); };
    el.appendChild(btn);
  });
}

function switchTab(btn, id) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  currentLayer = parseInt(id);
  renderLayer(id);
}

// ── Render keyboard ──
const LEFT_COLS = [0,1,2,3,4,5];
const RIGHT_COLS = [6,7,8,9,10,11];

function labelOf(b) {
  if (!b) return '?';
  b = b.trim();
  if (b === '&trans') return '↕';
  if (b === '&none') return '—';
  // strip leading &
  b = b.replace(/^&/, '');
  // shorten common patterns
  b = b.replace(/^kp\s+/, '');
  b = b.replace(/^mt\s+(\S+)\s+(\S+)/, (_, m, k) => shortenMod(m) + '/' + shorten(k));
  b = b.replace(/^lt\s+(\d+)\s+(\S+)/, (_, l, k) => 'L' + l + '/' + shorten(k));
  b = b.replace(/^to\s+(\d+)/, (_, l) => '→L' + l);
  b = b.replace(/^mkp\s+/, '🖱');
  b = b.replace(/^msc\s+/, '↕');
  b = b.replace(/^bt\s+BT_SEL\s+(\d)/, (_, n) => 'BT' + (parseInt(n)+1));
  b = b.replace(/^bt\s+BT_CLR/, 'BT CLR');
  b = b.replace(/^LS\((.+)\)/, 'S+$1');
  b = b.replace(/^LA\((.+)\)/, 'A+$1');
  return shorten(b);
}
function shorten(s) {
  const map = {LEFT_CONTROL:'Ctrl',LEFT_SHIFT:'⇧',LEFT_ALT:'Alt',LEFT_WIN:'WIN',
               RIGHT_SHIFT:'RS',RIGHT_ALT:'RAlt',
               LSHFT:'⇧',LCTRL:'Ctrl',LALT:'Alt',
               SPACE:'SPC',ENTER:'⏎',BSPC:'BS',DELETE:'DEL',
               MINUS:'－',COMMA:'，',DOT:'．',SLASH:'/',
               SEMI:'；',SQT:'：',INT_YEN:'¥\\',
               PAGE_UP:'PgUp',PAGE_DOWN:'PgDn',UP_ARROW:'↑',DOWN:'↓',
               LEFT:'←',RIGHT_ARROW:'→',HOME:'Home',END:'End',
               BACKSLASH:'\\',LEFT_BRACKET:'[',RIGHT_BRACKET:']',
               C_VOLUME_UP:'VOL+',C_VOLUME_DOWN:'VOL-',K_MUTE:'MUTE',
               LANG1:'IME',LANG2:'IME'};
  return map[s] || s;
}
function shortenMod(m) {
  return {LEFT_CONTROL:'C',LEFT_SHIFT:'S',LEFT_ALT:'A',RIGHT_SHIFT:'RS',RIGHT_ALT:'RA',
          LANG2:'IME',LANG1:'IME'}[m] || m.slice(0,2);
}

function isModified(layerId, idx) {
  const orig = (originalLayers[layerId] || [])[idx];
  const cur  = (layers[layerId] || [])[idx];
  return orig !== cur;
}

function makeKey(b, layerId, idx) {
  const lbl = labelOf(b);
  const empty = (b === '&trans' || b === '&none');
  const mod   = isModified(layerId, idx);
  const cls   = ['key', empty ? 'empty' : '', mod ? 'modified' : ''].filter(Boolean).join(' ');
  return `<div class="${cls}" title="${b}" onclick="openKeyModal(${layerId},${idx})">${lbl}</div>`;
}

function renderLayer(id) {
  id = parseInt(id);
  const bindings = layers[id] || [];
  const area = document.getElementById('kb-area');

  const m = meta[id] || {};
  let html = `<div class="layer-hint">${m.trigger || ''}</div><div class="kb">`;

  // Main rows: 3 rows of 12 (indices 0-35)
  for (let row = 0; row < 3; row++) {
    html += '<div class="kb-row">';
    // left 6
    for (let col = 0; col < 6; col++) {
      const idx = row * 12 + col;
      html += makeKey(bindings[idx] || '&none', id, idx);
    }
    html += '<div class="gap">⁞</div>';
    // right 6
    for (let col = 6; col < 12; col++) {
      const idx = row * 12 + col;
      html += makeKey(bindings[idx] || '&none', id, idx);
    }
    html += '</div>';
  }

  // Thumb row: indices 36-43 (left 5, right 3)
  html += '<div class="thumb-row">';
  for (let i = 36; i < 41; i++) {
    html += `<div style="width:60px">` + makeKey(bindings[i] || '&none', id, i) + '</div>';
  }
  html += '<div style="width:36px"></div>';
  for (let i = 41; i < 44; i++) {
    html += `<div style="width:60px">` + makeKey(bindings[i] || '&none', id, i) + '</div>';
  }
  html += '</div>';

  html += '</div>';
  area.innerHTML = html;
}

// ── Key edit modal ──
function openKeyModal(layerId, keyIdx) {
  editingKey = {layerId, keyIdx};
  const b = (layers[layerId] || [])[keyIdx] || '&none';
  document.getElementById('modal-title').textContent =
    `キー #${keyIdx} を編集（${(meta[layerId]||{}).name||'L'+layerId}）`;
  document.getElementById('binding-input').value = b;
  document.getElementById('binding-preset').value = '';
  document.getElementById('key-modal').classList.add('show');
  document.getElementById('binding-input').focus();
}

function applyPreset() {
  const val = document.getElementById('binding-preset').value;
  if (val) document.getElementById('binding-input').value = val;
}

function applyEdit() {
  if (!editingKey) return;
  const val = document.getElementById('binding-input').value.trim();
  if (!val) return;
  if (!layers[editingKey.layerId]) layers[editingKey.layerId] = [];
  layers[editingKey.layerId][editingKey.keyIdx] = val;
  closeModal();
  renderLayer(currentLayer);
}

function closeModal() {
  document.getElementById('key-modal').classList.remove('show');
  document.getElementById('binding-preset').value = '';
}

// Enter key in input
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeModal();
    document.getElementById('push-modal').classList.remove('show');
  }
  if (e.key === 'Enter' && document.getElementById('key-modal').classList.contains('show')) {
    applyEdit();
  }
});

// ── Save / Diff / Push ──
async function saveToFile() {
  setStatus('保存中...', '');
  const r = await fetch('/api/save', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({layers})
  });
  const d = await r.json();
  if (d.ok) {
    setStatus('✓ ファイルを保存しました', 'ok');
  } else {
    setStatus('❌ 保存失敗', 'err');
  }
}

async function showDiff() {
  const box = document.getElementById('diff-box');
  box.style.display = 'block';
  box.textContent = '取得中...';
  const r = await fetch('/api/diff');
  const d = await r.json();
  // Colorize diff
  const lines = d.diff.split('\n').map(l => {
    if (l.startsWith('+')) return `<span class="diff-add">${esc(l)}</span>`;
    if (l.startsWith('-')) return `<span class="diff-del">${esc(l)}</span>`;
    if (l.startsWith('@') || l.startsWith('diff') || l.startsWith('index'))
      return `<span class="diff-meta">${esc(l)}</span>`;
    return esc(l);
  });
  box.innerHTML = lines.join('\n');
}

function esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function openPushModal() {
  document.getElementById('push-status').textContent = '';
  document.getElementById('push-modal').classList.add('show');
}

async function doPush() {
  const msg = document.getElementById('commit-msg').value;
  document.getElementById('push-status').textContent = 'Push中...';
  document.getElementById('push-status').className = 'status';
  const r = await fetch('/api/push', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({message: msg})
  });
  const d = await r.json();
  const st = document.getElementById('push-status');
  if (d.ok) {
    st.textContent = '✓ Push完了！';
    st.className = 'status ok';
    originalLayers = JSON.parse(JSON.stringify(layers));
  } else {
    st.textContent = '❌ Push失敗: ' + d.output;
    st.className = 'status err';
  }
}

async function reloadFromFile() {
  const r = await fetch('/api/layers');
  const d = await r.json();
  layers = d.layers;
  originalLayers = JSON.parse(JSON.stringify(layers));
  buildTabs();
  renderLayer(currentLayer);
  setStatus('ファイルから再読み込みしました', 'ok');
}

function setStatus(msg, cls) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = 'status ' + cls;
}

// Click outside modal to close
document.getElementById('key-modal').addEventListener('click', function(e) {
  if (e.target === this) closeModal();
});
document.getElementById('push-modal').addEventListener('click', function(e) {
  if (e.target === this) this.classList.remove('show');
});

init();
</script>
</body>
</html>
"""

if __name__ == '__main__':
    print('=== okojyo_keyboard Keymap Editor ===')
    print(f'Repo: {REPO}')
    print('Open: http://localhost:5001')
    print('Ctrl+C to stop')
    # Open browser after 1 second
    def open_browser():
        import time; time.sleep(1)
        webbrowser.open('http://localhost:5001')
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(port=5001, debug=False)
