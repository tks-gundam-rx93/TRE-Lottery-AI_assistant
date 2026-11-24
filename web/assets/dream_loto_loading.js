/* TRE-Lottery: 夢ロトくんに着想を得たSCAN待機演出。
 * 公開写真・実機の仕組みを参考に、上部攪拌→遠心回転盤→1球ずつ排出をCanvasで表す。
 * 実抽せんの物理シミュレーターではない。番号は既存APIが確定させた第1候補のみを表示。
 * ランダムに「当せん」させる演出ではなく、予測結果との不整合を防ぐ。
 */
(function () {
  'use strict';

  const WIDTH = 640;
  const HEIGHT = 384;
  const MAX_NUMBER = 37;
  const MAIN_COUNT = 7;
  const TAU = Math.PI * 2;
  const ballColors = ['#edf7fc', '#f5dc62', '#41c68d', '#f47b82',
    '#5a94ee', '#eaa0d1', '#bc81e6'];

  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const clamp = x => Math.max(0, Math.min(1, x));

  function drawBall(ctx, x, y, radius, number, opacity = 1) {
    if (opacity <= 0) return;
    const color = ballColors[Math.min(6, Math.floor((number - 1) / 5))];
    ctx.save();
    ctx.globalAlpha = opacity;
    ctx.shadowColor = color;
    ctx.shadowBlur = 7;
    const g = ctx.createRadialGradient(x - radius * .35, y - radius * .4,
      radius * .06, x, y, radius);
    g.addColorStop(0, '#ffffff');
    g.addColorStop(.36, color);
    g.addColorStop(1, '#20334c');
    ctx.fillStyle = g;
    ctx.strokeStyle = '#c7eaff';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, TAU);
    ctx.fill();
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.fillStyle = '#102033';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = 'bold ' + Math.max(7, radius * .85) + 'px Arial, sans-serif';
    ctx.fillText(String(number).padStart(2, '0'), x, y + .5);
    ctx.restore();
  }

  class DreamLotoLoading {
    constructor() {
      this.active = false;
      this.frame = 0;
      this.selected = [];
      this.inFlight = null;
      this.startAt = 0;
      this.reducedMotion = !!(window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    }

    build() {
      if (this.root) return;
      const root = document.createElement('div');
      root.className = 'dream-loto-loading';
      root.hidden = true;
      root.id = 'dream-loto-scan';
      root.setAttribute('role', 'status');
      root.setAttribute('aria-label', 'ロト7の予測処理中');
      root.innerHTML = [
        '<section class="dream-loto-loading__panel">',
        '<div class="dream-loto-loading__title">◈ LOTO7 SCAN中...</div>',
        '<div class="dream-loto-loading__step" id="dream-loto-phase">01 / 37球を攪拌中</div>',
        '<div class="dream-loto-loading__machine">',
        '<canvas class="dream-loto-loading__canvas" id="dream-loto-canvas" width="640" height="384" aria-label="抽せん機風のボール攪拌と遠心回転のアニメーション"></canvas>',
        '</div>',
        '<div class="dream-loto-loading__track" id="dream-loto-track" aria-label="取り出した7つの番号"></div>',
        '<div class="dream-loto-loading__progress" id="dream-loto-progress">統計解析・MLP学習・3AI判定を実行しています</div>',
        '<p class="dream-loto-loading__warning">抽せん機の動きを参考にした表示演出です。実際の抽せん・当せんを再現するものではありません。</p>',
        '</section>'
      ].join('');
      document.body.appendChild(root);
      this.root = root;
      this.canvas = root.querySelector('#dream-loto-canvas');
      this.ctx = this.canvas.getContext('2d');
      this.phase = root.querySelector('#dream-loto-phase');
      this.progress = root.querySelector('#dream-loto-progress');
      this.track = root.querySelector('#dream-loto-track');
      // 高DPI画面でも文字・番号ボールがぼけないようにする。
      if (this.ctx) {
        const ratio = Math.min(2, window.devicePixelRatio || 1);
        this.canvas.width = WIDTH * ratio;
        this.canvas.height = HEIGHT * ratio;
        this.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      }
    }

    show() {
      this.build();
      this.active = true;
      this.selected = [];
      this.inFlight = null;
      this.startAt = performance.now();
      this.root.hidden = false;
      this.phase.textContent = '01 / 37球を攪拌中';
      this.progress.textContent = '統計解析・MLP学習・3AI判定を実行しています';
      this.renderTrack();
      cancelAnimationFrame(this.frame);
      if (this.ctx && !this.reducedMotion) this.animate();
      else if (this.ctx) this.render(this.startAt + 2500);
    }

    renderTrack() {
      this.track.replaceChildren();
      for (const n of this.selected) {
        const el = document.createElement('span');
        el.className = 'dream-loto-loading__ball';
        el.textContent = String(n).padStart(2, '0');
        this.track.appendChild(el);
      }
      for (let i = this.selected.length; i < MAIN_COUNT; i++) {
        const empty = document.createElement('span');
        empty.className = 'dream-loto-loading__slot';
        empty.textContent = String(i + 1);
        this.track.appendChild(empty);
      }
    }

    animate() {
      if (!this.active) return;
      this.render(performance.now());
      this.frame = requestAnimationFrame(() => this.animate());
    }

    render(now) {
      const ctx = this.ctx;
      if (!ctx) return;
      const t = (now - this.startAt) / 1000;
      ctx.clearRect(0, 0, WIDTH, HEIGHT);

      // ガラスケースの支柱・側面：実機に似た透明の二段構造。
      ctx.fillStyle = '#0a192744';
      ctx.fillRect(70, 35, 490, 318);
      ctx.strokeStyle = '#8bcbd65c';
      ctx.lineWidth = 2;
      ctx.strokeRect(70, 35, 490, 318);
      for (const post of [92, 535]) {
        ctx.strokeStyle = '#77cbdc88';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(post, 42); ctx.lineTo(post, 346); ctx.stroke();
      }

      // 上部球形の攪拌器（約55rpmを視覚モデルの角速度に採用）。
      ctx.save();
      ctx.strokeStyle = '#b1ebf6b9';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(295, 127, 88, 0, TAU);
      ctx.stroke();
      ctx.strokeStyle = '#48dcdf35';
      ctx.beginPath();
      ctx.ellipse(295, 127, 88, 29, t * .22, 0, TAU);
      ctx.stroke();
      ctx.restore();

      // 上部から下部の抽せん皿へ球が落ちる導入口。
      ctx.strokeStyle = '#8ee5fb85';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(277, 215); ctx.lineTo(277, 246);
      ctx.moveTo(313, 215); ctx.lineTo(313, 246);
      ctx.stroke();

      // 中央の回転皿。遠心力で外側を巡る球の速さは約90rpm相当。
      const diskCenter = {x: 295, y: 289};
      ctx.fillStyle = '#183f50aa';
      ctx.strokeStyle = '#b8f2ffbd';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.ellipse(diskCenter.x, diskCenter.y, 179, 52, 0, 0, TAU);
      ctx.fill(); ctx.stroke();
      ctx.strokeStyle = '#35e3ca70';
      ctx.lineWidth = 1;
      for (let r = 57; r <= 155; r += 49) {
        ctx.beginPath();
        ctx.ellipse(diskCenter.x, diskCenter.y, r, r * .29, 0, 0, TAU);
        ctx.stroke();
      }
      ctx.strokeStyle = '#baf7ea90';
      for (let k = 0; k < 8; k++) {
        const a = t * TAU * 1.5 + TAU * k / 8;
        ctx.beginPath();
        ctx.moveTo(diskCenter.x, diskCenter.y);
        ctx.lineTo(diskCenter.x + 164 * Math.cos(a),
          diskCenter.y + 45 * Math.sin(a));
        ctx.stroke();
      }

      // 37球の攪拌→落下→遠心回転。
      // 途中の球を個別にずらして移動させ、急な瞬間移動を避ける。
      const chosen = new Set(this.selected);
      if (this.inFlight) chosen.add(this.inFlight.number);
      for (let i = 0; i < MAX_NUMBER; i++) {
        const number = i + 1;
        if (chosen.has(number)) continue;
        const a = TAU * i / MAX_NUMBER;
        const upperAngle = a + t * TAU * 55 / 60;
        const lowerAngle = a + t * TAU * 90 / 60;
        const ux = 295 + Math.cos(upperAngle) * 65;
        const uy = 127 + Math.sin(upperAngle) * 60;
        const lx = 295 + Math.cos(lowerAngle) * (144 + 10 * Math.sin(i * 3.7));
        const ly = 289 + Math.sin(lowerAngle) * 38;
        const transfer = clamp((t - 1.0 - i * .013) / .95);
        const smooth = transfer * transfer * (3 - 2 * transfer);
        const x = ux * (1 - smooth) + lx * smooth;
        const y = uy * (1 - smooth) + ly * smooth;
        drawBall(ctx, x, y, 9.2, number, .9);
      }

      // 排出口・取り出しレール。
      ctx.strokeStyle = '#ffd777db';
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.moveTo(468, 276); ctx.lineTo(555, 276); ctx.lineTo(578, 295);
      ctx.stroke();
      ctx.fillStyle = '#ffc76d';
      ctx.fillRect(466, 270, 13, 12);
      if (this.inFlight) {
        const u = clamp((now - this.inFlight.start) / 330);
        const ease = u * u * (3 - 2 * u);
        const x = 472 + 101 * ease;
        const y = 276 + 19 * ease - 18 * Math.sin(u * Math.PI);
        drawBall(ctx, x, y, 16, this.inFlight.number);
      }

      // ラベルと通電インジケーター。
      ctx.fillStyle = '#b1f1ff';
      ctx.font = 'bold 13px Courier New, monospace';
      ctx.textAlign = 'center';
      ctx.fillText('YUME LOTO / SCAN SIMULATION', 320, 26);
      ctx.font = '12px Courier New, monospace';
      ctx.fillStyle = '#65d7e0';
      ctx.fillText('AGITATION', 171, 130);
      ctx.fillText('CENTRIFUGAL ROTOR', 310, 367);
      ctx.fillStyle = '#56f0a2';
      ctx.beginPath();
      ctx.arc(531, 58, 5 + Math.sin(t * 8) * 1.5, 0, TAU);
      ctx.fill();
    }

    async reveal(numbers) {
      if (!this.active) return;
      if (!Array.isArray(numbers) || numbers.length !== MAIN_COUNT ||
          new Set(numbers).size !== MAIN_COUNT ||
          numbers.some(n => !Number.isInteger(n) || n < 1 || n > MAX_NUMBER)) {
        throw new Error('予測結果の7数字が不正です');
      }
      this.phase.textContent = '02 / 遠心回転盤から本数字を抽出';
      this.progress.textContent = '解析完了 / 予測第1候補を7球の演出で表示しています';
      // APIが高速に応答した場合でも、攪拌→遠心回転の順を崩さない。
      const elapsed = performance.now() - this.startAt;
      if (!this.reducedMotion && elapsed < 2300) await sleep(2300 - elapsed);
      if (!this.active) return;

      // 実際の候補に含まれる7球のみを演出する。抽出順はランダムだが内容は一致する。
      const sequence = numbers.slice();
      for (let i = sequence.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [sequence[i], sequence[j]] = [sequence[j], sequence[i]];
      }
      for (const n of sequence) {
        if (!this.active) break;
        this.inFlight = {number:n, start:performance.now()};
        if (!this.reducedMotion) await sleep(350);
        if (!this.active) break;
        this.inFlight = null;
        this.selected.push(n);
        this.renderTrack();
        this.progress.textContent = '本数字 '+this.selected.length+' / 7球を表示中';
        if (!this.reducedMotion) await sleep(90);
      }
      if (!this.active) return;
      this.phase.textContent = '03 / SCAN完了';
      this.progress.textContent = '第1候補の7数字を表示しました。5通りの結果を開きます';
      if (!this.reducedMotion) await sleep(450);
    }

    hide() {
      this.active = false;
      this.inFlight = null;
      cancelAnimationFrame(this.frame);
      if (this.root) this.root.hidden = true;
    }
  }

  window.dreamLotoLoader = new DreamLotoLoading();
})();
