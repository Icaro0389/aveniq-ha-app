const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');
const source = fs.readFileSync('aveniq/app/static/assets/app.js','utf8').replace(/render\(\);loadSharedConfig\(\);refresh\(\);setInterval\(\(\)=>\{if\(!requestRunning\)refresh\(\)\},8000\);\s*$/, '');
const storage={};
const ctx={console,document:{querySelector:()=>({innerHTML:'',classList:{toggle(){}}}),querySelectorAll:()=>[],body:{classList:{toggle(){}},insertAdjacentHTML(){}},addEventListener(){}},window:{},localStorage:{getItem:(k)=>storage[k]||null,setItem:(k,v)=>storage[k]=v},setTimeout,clearTimeout,setInterval:()=>{},fetch:()=>Promise.reject(new Error('offline')),URL,Blob};
vm.createContext(ctx);
vm.runInContext(source,ctx);
test('climate premium generates live setpoint dial',()=>{
 const result=vm.runInContext("(()=>{states[E.thermo]={state:'heat',attributes:{temperature:21.5,current_temperature:20.5,min_temp:7,max_temp:30,hvac_modes:['off','heat']}};return climatePremium(E.thermo,'Netatmo','warm')})()",ctx);
 assert.match(result,/climate-dial/);assert.match(result,/21.5/);assert.match(result,/Riscaldamento/);
});
test('Alarmo controls remain available',()=>{
 const result=vm.runInContext("alarmModal()",ctx);
 assert.match(result,/alarm_arm_away/);assert.match(result,/alarm_disarm/);
});
test('Nuki commands remain available',()=>{
 const result=vm.runInContext("(()=>{states[E.door]={state:'locked',attributes:{supported_features:1}};return details.door()})()",ctx);
 assert.match(result,/Sblocca/);assert.match(result,/Apri porta/);
});
test('room default assignment and widget UI render',()=>{
 const result=vm.runInContext("homeRooms()+widgetManager()",ctx);
 assert.match(result,/Salotto/);assert.match(result,/Widget Studio/);
});
test('Kodi empty state is explicit',()=>{
 const result=vm.runInContext("kodiRemote()",ctx);
 assert.match(result,/Nessuna entità media_player Kodi/);
});

test('Kodi D-pad uses allowlisted input methods',()=>{
 const result=vm.runInContext("(()=>{states['media_player.kodi']={state:'idle',attributes:{friendly_name:'Kodi'}};return kodiRemote()})()",ctx);
 assert.match(result,/Input.Up/);
 assert.match(result,/Input.Select/);
 assert.match(result,/Input.ContextMenu/);
});
test('widget resize and drag handles render',()=>{
 const result=vm.runInContext("(()=>{view='impostazioni';widgetConfigs=[{type:'energy',entity:'sensor.test',span:2,title:'Energia'}];return widgetsBlock()})()",ctx);
 assert.match(result,/widget-span-2/);
 assert.match(result,/data-widget-resize/);
 assert.match(result,/draggable="true"/);
});
