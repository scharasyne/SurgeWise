import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateStyleMin } from '@maplibre/maplibre-gl-style-spec';
import { SATELLITE_IMAGERY, dashboardLayerPaint, hiddenOverImagery, imageryLayerPaint } from './dashboard-map-style.ts';

const line = (id, sourceLayer = 'transportation') => ({ id, type: 'line', source: 'openmaptiles', 'source-layer': sourceLayer });

test('imagery source and layer satisfy the MapLibre style contract and carry attribution', () => {
  const { layerId, sourceId, ...source } = SATELLITE_IMAGERY;
  const style = { version: 8, sources: { [sourceId]: { type: 'raster', ...source } }, layers: [{ id: layerId, type: 'raster', source: sourceId }] };
  assert.deepEqual(validateStyleMin(style).map(error => error.message), []);
  assert.match(SATELLITE_IMAGERY.attribution, /Esri/);
  assert.match(SATELLITE_IMAGERY.tiles[0], /^https:\/\/.*\{z\}\/\{y\}\/\{x\}$/);
});

test('minor roads, rails and casings are hidden over imagery; major roads stay', () => {
  for (const id of ['road_minor', 'road_service_track', 'road_trunk_primary_casing', 'road_major_rail', 'tunnel_motorway', 'road_one_way_arrow'])
    assert.equal(hiddenOverImagery(line(id)), true, id);
  for (const id of ['road_motorway', 'road_trunk_primary', 'road_secondary_tertiary', 'bridge_motorway'])
    assert.equal(hiddenOverImagery(line(id)), false, id);
  assert.equal(hiddenOverImagery({ id: 'water', type: 'fill', source: 'openmaptiles', 'source-layer': 'water' }), false);
});

test('labels turn light with dark halos over imagery and revert to the street palette', () => {
  const label = { id: 'label_village', type: 'symbol', source: 'openmaptiles', 'source-layer': 'place', layout: { 'text-field': '{name}' } };
  assert.equal(imageryLayerPaint(label)['text-color'], '#ffffff');
  assert.equal(dashboardLayerPaint(label)['text-color'], '#536d6b');
  assert.equal(imageryLayerPaint(line('road_motorway'))['line-color'], '#f2c45a');
  assert.deepEqual(imageryLayerPaint({ id: 'water', type: 'fill', 'source-layer': 'water' }), dashboardLayerPaint({ id: 'water', type: 'fill', 'source-layer': 'water' }));
});
