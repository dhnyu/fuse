const fs=require('fs'),vm=require('vm'),assert=require('assert');
const context={console,setTimeout,Map,Set,Promise,cache:new Map(),config:{files:{}},details:()=>{},calls:0,fail:false};context.window=context;
context.verified=async path=>{context.calls++;if(context.fail)throw Error('fixture');context.S10Perf.sizes.set(path,1024*1024);return {path}};
vm.createContext(context);vm.runInContext(fs.readFileSync('tools/retrieval_inspector/performance/runtime.js','utf8'),context);
(async()=>{
 const [a,b]=await Promise.all([context.artifact('same'),context.artifact('same')]);assert.strictEqual(a,b);assert.strictEqual(context.calls,1);
 context.S10Perf.pinned=new Set(['same']);for(let i=0;i<50;i++)await context.artifact('scene'+i);
 assert(context.cache.size<=16);assert(context.cache.has('same'));assert(context.S10Perf.cacheBytes<=context.S10Perf.budget);
 context.fail=true;await assert.rejects(context.artifact('broken'));context.fail=false;await context.artifact('broken');
 assert(context.cache.has('broken'));console.log('bounded cache/coalescing/pinning/error retry PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
