import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { CITY_BOUNDARY_STYLE, DEFAULT_QC_VIEW, QC_EXTENT_VIEW, defaultSimulationCamera, fitZoom, simulationMapPadding, selectionMapBounds } from './simulation-map.ts';

test('wide status overlays reserve the top of the map, without consuming its left side', () => {
  const padding = simulationMapPadding(1000,700,[{ left:18,top:80,width:620,height:70 }]);
  assert.ok(padding.top>=160);
  assert.ok(padding.left<100);
  assert.ok(padding.left+padding.right<1000-100);
});

test('selection framing includes every linked endpoint and the complete selected polygon bounds', () => {
  const endpoints = [[121.02,14.64],[121.07,14.67],[121.09,14.65]];
  assert.deepEqual(selectionMapBounds(endpoints, [[121.01,14.63],[121.08,14.69]]), [[121.01,14.63],[121.09,14.69]]);
  assert.deepEqual(selectionMapBounds([[121.05,14.65]]), [[121.05,14.65],[121.05,14.65]]);
  assert.equal(selectionMapBounds([]), null);
  assert.equal(selectionMapBounds([[NaN,14.65]]), null);
  assert.equal(selectionMapBounds([[181,14.65]]), null);
});

test('default Simulation view keeps the user-chosen centre and all of Quezon City east-west', () => {
  const [[west,south],[east,north]] = DEFAULT_QC_VIEW;
  assert.ok(Math.abs((west+east)/2-121.051)<0.001 && Math.abs((south+north)/2-14.6755)<0.001,'centre of the chosen view');
  assert.ok(west<=121.0 && east>=121.153,'QC longitude extent stays inside the default view');
  assert.ok(south<north && west<east);
});

test('wide screens open on the chosen view, centred, with the latitude range filling the height', () => {
  const overlays = width => [{left:width-120,top:18,width:100,height:44},{left:18,top:18,width:190,height:54}];
  for(const [width,height] of [[1845,728],[1100,450]]) {
    const camera = defaultSimulationCamera(width,height,overlays(width));
    assert.deepEqual(camera.bounds,DEFAULT_QC_VIEW);
    assert.equal(camera.padding.top,0); assert.equal(camera.padding.bottom,0);
    assert.equal(camera.padding.left,camera.padding.right,'equal sides keep the view centred');
  }
  // The user's 1827×716 map reproduces the screenshot zoom (≈11.45) to within a few percent.
  const camera = defaultSimulationCamera(1827,716,overlays(1827));
  assert.ok(Math.abs(fitZoom(camera.bounds,1827,716,camera.padding)-11.45)<0.06);
});

test('narrow screens fit Quezon City itself instead of zooming out to the wide view', () => {
  const camera = defaultSimulationCamera(430,587,[{left:374,top:290,width:44,height:240}]);
  assert.deepEqual(camera.bounds,QC_EXTENT_VIEW);
  assert.ok(fitZoom(QC_EXTENT_VIEW,430,587,camera.padding)>fitZoom(DEFAULT_QC_VIEW,430,587,{top:0,bottom:0,left:107,right:107}));
  assert.ok(Number.isFinite(fitZoom(QC_EXTENT_VIEW,10,10,{top:20,bottom:20,left:20,right:20})),'degenerate viewports stay finite');
});

test('Simulation city outlines use the Dashboard source and style, starting hidden', () => {
  const simulation = readFileSync(new URL('../components/outbreak-map.tsx', import.meta.url), 'utf8');
  const dashboard = readFileSync(new URL('../components/ncr-map.tsx', import.meta.url), 'utf8');
  for (const source of [simulation, dashboard]) assert.match(source, /fetch\('\/api\/boundaries'/);
  const { fill, line } = CITY_BOUNDARY_STYLE;
  for (const value of [fill.highlighted, fill.other]) {
    assert.ok(simulation.includes(`'${value}'`), `Simulation layer uses ${value}`);
    assert.ok(dashboard.includes(`'${value}'`), `Dashboard layer uses ${value}`);
  }
  assert.ok(simulation.includes(`'${line.color}'`));
  assert.match(dashboard, /CITY_BOUNDARY_STYLE\.line\.color/, 'Dashboard outline uses the shared colour');
  for (const value of [fill.highlightedOpacity, fill.otherOpacity, line.highlightedWidth, line.otherWidth]) assert.ok(simulation.includes(String(value)));
  assert.match(simulation, /id: 'city-fill'[^\n]*visibility: 'none'/);
  assert.match(simulation, /id: 'city-border'[^\n]*visibility: 'none'/);
});

test('camera padding leaves visible map space on narrow and short viewports', () => {
  for(const [width,height] of [[320,200],[390,350],[1100,450]]) {
    const padding = simulationMapPadding(width,height,[{left:width-50,top:68,width:45,height:170},{left:12,top:height-100,width:width-90,height:100}]);
    assert.ok(padding.left+padding.right<width*.65);
    assert.ok(padding.top+padding.bottom<height*.65);
    assert.ok(Object.values(padding).every(value=>Number.isFinite(value)&&value>=0));
  }
});
