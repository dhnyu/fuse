const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('tools/retrieval_inspector/composite_c/runtime.js','utf8');
const start=source.indexOf('class ByteLRU'),end=source.indexOf('const summaryCache',start);
const ctx={Map,Set,Promise,URL,Blob};vm.createContext(ctx);vm.runInContext(source.slice(start,end)+';globalThis.LRU=ByteLRU',ctx);
(async()=>{
 const cache=new ctx.LRU(100,4);let calls=0;
 const loader=async()=>{calls++;return {value:new Blob(['hello']),bytes:20}};
 const [a,b]=await Promise.all([cache.get('same',loader),cache.get('same',loader)]);assert.strictEqual(a,b);assert.equal(calls,1);cache.pins.add('same');
 for(let n=0;n<100;n++)await cache.get('key'+n,loader);
 assert(cache.map.has('same'));assert(cache.bytes<=100);assert(cache.map.size<=4);assert.equal(cache.pending.size,0);
 await assert.rejects(cache.get('broken',async()=>{throw Error('fixture')}));assert(!cache.pending.has('broken'));await cache.get('broken',loader);assert(cache.map.has('broken'));
 console.log('Composite cache: concurrent dedup, bounded retention, pinned main card, retry PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
