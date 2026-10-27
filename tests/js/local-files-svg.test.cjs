const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
test('SVG counts as accepted only in resolution, with a static <img> thumbnail',()=>{
 const context=vm.createContext({window:{},document:{readyState:'loading',addEventListener(){}}});
 const source=fs.readFileSync(path.join(__dirname,'../../app/static/js/local-files.js'),'utf8');
 vm.runInContext(source,context);
 const files=[{name:'produto.svg',size:100,webkitRelativePath:'Produtos/001/produto.svg'}];
 const result=context.window.PRMLocalFiles.classify(files,'imagens',true);
 assert.equal(result.files.length,1);assert.equal(result.ignored.length,0);
 assert.equal(result.files[0].path,'001/produto.svg');
 assert.equal(context.window.PRMLocalFiles.classify(files,'lote',true).ignored.length,1);
 assert.match(source,/filter\(f => IMAGES.includes/);
 // Thumbnails: SVG only in the resolution profile, and only through <img> (static, sandboxed by the browser).
 assert.match(source,/this\.profile === "imagens" && ext\(f\.path\) === "\.svg"/);
 assert.doesNotMatch(source,/innerHTML/);
});
