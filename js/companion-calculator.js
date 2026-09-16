(function(root){
  'use strict';
  const cents=value=>{if(value===''||value===null||typeof value==='boolean')throw Error('Enter a valid amount.');const n=Number(value);if(!Number.isFinite(n)||n<0||n>1000000)throw Error('Enter an amount from $0 to $1,000,000.');return Math.round(n*100)};
  function calculate(values){
    const primary=cents(values.primary),base=cents(values.base),taxes=cents(values.taxes);
    const regular=values.alternative===''||values.alternative==null?primary*2:cents(values.alternative);
    const companion=primary+base+taxes,extra=(values.includeFee?cents(values.fee):0)+cents(values.opportunity??0);
    return {regular:regular/100,companion:companion/100,extra:extra/100,tripSaving:(regular-companion)/100,netSaving:(regular-companion-extra)/100,breakEven:(companion+extra)/100};
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={calculate};
  root.CompanionCalculator={calculate};
  if(typeof document==='undefined')return;
  const publicHost=['practicalrewards.com','www.practicalrewards.com'].includes(location.hostname);
  if(publicHost){
    root.dataLayer=root.dataLayer||[];root.gtag=root.gtag||function(){root.dataLayer.push(arguments)};root.gtag('js',new Date());root.gtag('config','G-TXPB5KSTNP');
    const ga=document.createElement('script');ga.async=true;ga.src='https://www.googletagmanager.com/gtag/js?id=G-TXPB5KSTNP';document.head.appendChild(ga);
    root.clarity=root.clarity||function(){(root.clarity.q=root.clarity.q||[]).push(arguments)};const cl=document.createElement('script');cl.async=true;cl.src='https://www.clarity.ms/tag/t8qvj4h0gj';document.head.appendChild(cl);
  }
  const track=(event,params={})=>{if(publicHost&&typeof root.gtag==='function')root.gtag('event',event,{tool_name:'alaska_companion_fare',...params})};
  const $=id=>document.getElementById(id),money=value=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:value%1?2:0}).format(value);
  let touched=false,recorded=false;
  function render(){
    $('fee').disabled=!$('include-fee').checked;
    const values=Object.fromEntries(['primary','base','taxes','alternative','fee','opportunity'].map(k=>[k,$(k).value]));values.includeFee=$('include-fee').checked;
    $('alternative').placeholder=Number(values.primary)>=0?money(Number(values.primary)*2):'Total for two';
    try{
      const r=calculate(values);$('input-error').hidden=true;$('share-result').disabled=false;
      $('result-kind').textContent=touched?'YOUR ESTIMATE':'EXAMPLE RESULT';
      $('result-heading').textContent=r.extra?'After the card costs you included':'Your trip savings';
      $('savings').textContent=money(Math.abs(r.netSaving));
      $('verdict').textContent=r.netSaving>0?'Less than your two-ticket alternative.':r.netSaving<0?'More than your two-ticket alternative.':'The two options break even.';
      $('regular-total').textContent=money(r.regular);$('companion-total').textContent=money(r.companion);$('extra-total').textContent=money(r.extra);$('cost-row').hidden=!r.extra;$('trip-row').hidden=!r.extra;$('trip-saving').textContent=money(r.tripSaving);
      $('break-even').textContent='The two-ticket alternative must cost more than '+money(r.breakEven)+' for '+(r.extra?'the companion fare plus these card costs':'the companion fare')+' to save money.';
      if(touched&&!recorded){track('calculator_use');recorded=true}
    }catch(error){$('input-error').textContent=error.message;$('input-error').hidden=false;$('savings').textContent='—';$('verdict').textContent='Finish entering your amounts to see the comparison.';for(const id of ['regular-total','companion-total','extra-total','trip-saving'])$(id).textContent='—';$('break-even').textContent='';$('share-result').disabled=true;}
  }
  $('fare-form').addEventListener('submit',e=>e.preventDefault());$('fare-form').addEventListener('input',()=>{touched=true;render()});$('fare-form').addEventListener('reset',()=>{touched=false;setTimeout(render,0)});
  $('share-result').addEventListener('click',async()=>{const url='https://practicalrewards.com/calculators/alaska-companion-fare.html';try{if(navigator.share){await navigator.share({title:'Alaska Companion Fare Calculator',text:'See whether the companion fare beats what you would otherwise pay for two tickets.',url});$('share-status').textContent='';}else{await navigator.clipboard.writeText(url);$('share-status').textContent='Calculator link copied.'}track('calculator_share')}catch(error){if(error.name!=='AbortError')$('share-status').textContent='Share this link: '+url}});
  document.querySelectorAll('[data-calc-link]').forEach(a=>a.addEventListener('click',()=>track('calculator_next_step',{destination:a.dataset.calcLink})));
  render();
})(typeof window==='undefined'?globalThis:window);
