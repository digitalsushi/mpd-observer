export function temperatureGroups(readings,threshold=3){
 const sorted=readings.filter(r=>Number.isFinite(r.value)).sort((a,b)=>a.value-b.value);
 const groups=[];
 for(const reading of sorted){
  let group=groups.at(-1);
  // Bound the full group spread; do not chain 65,68,71 into a misleading single needle.
  if(!group||reading.value-group.members[0].value>threshold){group={members:[]};groups.push(group)}
  group.members.push(reading);
 }
 return groups.map(g=>({...g,value:g.members.reduce((sum,r)=>sum+r.value,0)/g.members.length}));
}
export function temperatureRange(values,min=20,max=100){
 const valid=values.filter(Number.isFinite);
 return {min:Math.min(min,...valid.map(v=>Math.floor(v/10)*10)),max:Math.max(max,...valid.map(v=>Math.ceil(v/10)*10))};
}
export function temperatureAngle(value,range){return -135+(value-range.min)/(range.max-range.min)*270}

export function thermometerFace(state,healthy,emergency){
 if(emergency)return '#ed302a';
 if(!healthy)return 'url(#face)';
 return ['below','plateau'].includes(state)?'#000080':'url(#face)';
}
