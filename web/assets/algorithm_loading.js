/* TRE-Lottery AI Assistant / SCAN four strategy visualization.
 *
 * FREQUENCY: simulated frequency bars; GAP_PAIR: changing number-pair graph;
 * MONTE_CARLO: reshuffled trial balls; DEEP_LEARNING: MLP signal propagation.
 *
 * NOTE: All moving visuals are EXPLANATORY, not measured server-side progress
 * or actual feature/weight values. The only calculated numbers shown are
 * validated top candidates in the /api/predict all_candidates payload.
 * The API itself computes each strategy sequentially.
 */
(function () {
  'use strict';

  const W = 160;
  const H = 76;
  const TAU = Math.PI * 2;
  const METHODS = [
    {key:'FREQUENCY', name:'FREQUENCY', subtitle:'20回・100回・全履歴の頻度'},
    {key:'GAP_PAIR', name:'GAP_PAIR', subtitle:'未出現間隔・数字のペア'},
    {key:'MONTE_CARLO', name:'MONTE_CARLO', subtitle:'乱数試行・分布の比較'},
    {key:'DEEP_LEARNING', name:'DEEP_LEARNING', subtitle:'MLP 111→32→16→37'}
  ];

  function circle(ctx,x,y,r,fill) {
    ctx.beginPath();
    ctx.arc(x,y,r,0,TAU);
    ctx.fillStyle=fill;
    ctx.fill();
  }
  function line(ctx,x1,y1,x2,y2,color,width=1) {
    ctx.beginPath();
    ctx.moveTo(x1,y1);
    ctx.lineTo(x2,y2);
    ctx.strokeStyle=color;
    ctx.lineWidth=width;
    ctx.stroke();
  }
  function text(ctx,s,x,y,color,size=9) {
    ctx.fillStyle=color;
    ctx.font='bold '+size+'px Courier New, monospace';
    ctx.textAlign='center';
    ctx.textBaseline='middle';
    ctx.fillText(s,x,y);
  }

  function frequency(ctx,t) {
    line(ctx,7,64,154,64,'#547d9299');
    for(let i=0;i<13;i++){
      const height=10+38*(.24+.37*Math.sin((i+1)*2.19+t*2.7)**2+
        .23*Math.sin(i*.68-t*.88)**2);
      const x=11+i*11;
      ctx.fillStyle=i%3===0?'#34e8b5':'#3eace1';
      ctx.globalAlpha=.66+.25*Math.sin(t*2+i*.8)**2;
      ctx.fillRect(x,63-height,7,height);
      ctx.globalAlpha=1;
    }
    text(ctx,'weighted frequency',79,9,'#85e6f6',9);
  }

  function gapPair(ctx,t) {
    const points=[];
    for(let i=0;i<7;i++){
      const a=i*TAU/7-Math.PI/2+t*.16;
      points.push([80+51*Math.cos(a),40+25*Math.sin(a)]);
    }
    const links=[[0,3],[1,5],[2,4],[3,6],[0,5],[1,4],[2,6]];
    links.forEach(([a,b],i)=>{
      line(ctx,...points[a],...points[b],
        i%2?'#64e9bc88':'#55b4f777',1.4);
    });
    points.forEach(([x,y],i)=>{
      circle(ctx,x,y,4+1.4*Math.sin(t*3+i)**2,
        i%2?'#8fedce':'#7dbfff');
    });
    text(ctx,'gap + pair links',80,9,'#85e6f6',9);
  }

  function monteCarlo(ctx,t) {
    const colors=['#ffffff','#f0d359','#79dfab','#f37f88',
      '#6895f6','#eaaaeb','#b488f4'];
    // The balls carry no digits to avoid presenting random animation as predictions.
    for(let i=0;i<7;i++){
      const a=t*(1.7+.21*(i%3))+i*TAU/7;
      const x=80+48*Math.sin(a+i*.3);
      const y=41+18*Math.cos(a*1.5+i*.73);
      circle(ctx,x,y,5.5,colors[i]);
      circle(ctx,x-1.5,y-2,1.5,'#ffffffbb');
    }
    text(ctx,'random sampling',80,9,'#85e6f6',9);
  }

  function mlp(ctx,t) {
    const counts=[4,5,4,5];
    const xs=[15,58,102,147];
    const nodes=counts.map((cnt,layer)=>Array.from({length:cnt},(_,i)=>({
      x:xs[layer],
      y:22+(i-(cnt-1)/2)*10.7
    })));
    for(let l=0;l<3;l++){
      for(let i=0;i<nodes[l].length;i++){
        for(let j=0;j<nodes[l+1].length;j++){
          const a=nodes[l][i],b=nodes[l+1][j];
          const phase=(Math.sin(t*4.5-l*1.8-i*.67+j*.53)+1)/2;
          line(ctx,a.x,a.y,b.x,b.y,
            phase>.57?'#60efb777':'#4588a445',phase>.8?1.4:.75);
        }
      }
    }
    nodes.forEach((layer,l)=>layer.forEach((n,i)=>{
      const active=(Math.sin(t*5-l*1.4-i*.6)+1)/2;
      circle(ctx,n.x,n.y,2.6,active>.55?'#8affc4':'#6fabc9');
    }));
    ['111','32','16','37'].forEach((x,i)=>text(ctx,x,xs[i],69,'#8bc6e3',8));
    text(ctx,'neural signals',80,9,'#85e6f6',9);
  }

  class AlgorithmLoading {
    constructor(){
      this.active=false;
      this.frame=0;
      this.startAt=0;
      this.lastDrawAt=0;
      this.reducedMotion=!!(window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    }
    mount(){
      const overlay=document.getElementById('dream-loto-scan');
      if(!overlay)throw Error('SCANアニメーションを初期化できません');
      if(this.container&&overlay.contains(this.container))return;
      const machine=overlay.querySelector('.dream-loto-loading__machine');
      if(!machine)throw Error('抽せん機パネルが見つかりません');
      const region=document.createElement('section');
      region.className='dream-algorithms';
      region.id='dream-algorithms';
      region.setAttribute('aria-label','4種類のアルゴリズムの可視化');
      this.cards={};
      this.contexts={};
      const ratio=Math.min(2,window.devicePixelRatio||1);
      for(const method of METHODS){
        const card=document.createElement('div');
        card.className='dream-algorithms__card';
        card.dataset.method=method.key;
        card.dataset.state='running';
        const heading=document.createElement('div');
        heading.className='dream-algorithms__title';
        const lamp=document.createElement('span');
        lamp.className='dream-algorithms__lamp';
        lamp.setAttribute('aria-hidden','true');
        const name=document.createElement('span');
        name.textContent=method.name;
        heading.append(lamp,name);
        const desc=document.createElement('div');
        desc.className='dream-algorithms__subtitle';
        desc.textContent=method.subtitle;
        const canvas=document.createElement('canvas');
        canvas.className='dream-algorithms__canvas';
        canvas.width=W*ratio;
        canvas.height=H*ratio;
        canvas.setAttribute('aria-hidden','true');
        const status=document.createElement('div');
        status.className='dream-algorithms__state';
        status.textContent='計算イメージ';
        status.setAttribute('aria-live','polite');
        card.append(heading,desc,canvas,status);
        region.appendChild(card);
        this.cards[method.key]={card,status};
        const ctx=canvas.getContext('2d');
        if(ctx){
          ctx.setTransform(ratio,0,0,ratio,0,0);
          this.contexts[method.key]=ctx;
        }
      }
      const note=document.createElement('div');
      note.className='dream-algorithms__note';
      note.textContent='※ 動きは各方式の概念図です。実際の進捗率・並列処理を示しません。';
      region.appendChild(note);
      machine.insertAdjacentElement('afterend',region);
      this.container=region;
    }
    begin(){
      this.mount();
      cancelAnimationFrame(this.frame);
      this.active=true;
      this.startAt=performance.now();
      this.lastDrawAt=0;
      for(const method of METHODS){
        const {card,status}=this.cards[method.key];
        card.dataset.state='running';
        status.textContent='計算イメージ';
      }
      this.draw(this.startAt);
      if(!this.reducedMotion)this.loop();
    }
    loop(){
      if(!this.active)return;
      const now=performance.now();
      // Throttle the four small canvases to <= 30fps, reduce battery/CPU usage.
      if(now-this.lastDrawAt>=33){
        this.draw(now);
        this.lastDrawAt=now;
      }
      this.frame=requestAnimationFrame(()=>this.loop());
    }
    draw(now){
      const t=(now-this.startAt)/1000;
      const fns={
        FREQUENCY:frequency, GAP_PAIR:gapPair,
        MONTE_CARLO:monteCarlo, DEEP_LEARNING:mlp
      };
      for(const method of METHODS){
        const ctx=this.contexts[method.key];
        if(!ctx)continue;
        ctx.clearRect(0,0,W,H);
        fns[method.key](ctx,t);
      }
    }
    resolve(result){
      if(!this.active)return;
      const all=Array.isArray(result&&result.all_candidates)?
        result.all_candidates:[];
      for(const method of METHODS){
        const {card,status}=this.cards[method.key];
        const candidate=all.find(c=>c&&c.method===method.key&&
          Array.isArray(c.numbers)&&c.numbers.length===7&&
          new Set(c.numbers).size===7&&
          c.numbers.every(n=>Number.isInteger(n)&&n>=1&&n<=37));
        if(!candidate){
          card.dataset.state='skipped';
          status.textContent=method.key==='DEEP_LEARNING'?
            '履歴不足などで対象外':'今回の候補なし';
          continue;
        }
        card.dataset.state='complete';
        status.textContent='実候補: '+
          candidate.numbers.map(n=>String(n).padStart(2,'0')).join(' ');
      }
    }
    end(){
      this.active=false;
      cancelAnimationFrame(this.frame);
    }
  }
  window.dreamLotoAlgorithms=new AlgorithmLoading();
})();
