import type { LayerSpecification, Map as MapLibreMap } from 'maplibre-gl';

/** Cartographic context only. These colors never encode disease or capacity. */
export function dashboardLayerPaint(layer: LayerSpecification): Record<string, string | number> {
  const sourceLayer = 'source-layer' in layer ? layer['source-layer'] : '';
  if (layer.type === 'background') return { 'background-color': '#eef2ef' };
  if (layer.type === 'raster') return { 'raster-opacity': 0 };
  if (layer.type === 'fill-extrusion') return { 'fill-extrusion-color': '#a9bdbb', 'fill-extrusion-opacity': 0.86 };
  if (layer.type === 'fill') {
    if (sourceLayer === 'water') return { 'fill-color': '#9bc8cc' };
    if (sourceLayer === 'park' || sourceLayer === 'landcover') return { 'fill-color': '#d5e3d3', 'fill-opacity': 0.65 };
    if (layer.id === 'landuse_hospital') return { 'fill-color': '#d2e5df' };
    if (sourceLayer === 'landuse') return { 'fill-color': '#e4e9e1' };
    if (sourceLayer === 'building') return { 'fill-color': '#c0cecc', 'fill-outline-color': '#adbfbc' };
    return {};
  }
  if (layer.type === 'line') {
    if (sourceLayer === 'waterway') return { 'line-color': '#9bc8cc' };
    if (sourceLayer === 'park') return { 'line-color': '#c9dbc7' };
    if (sourceLayer === 'boundary') return { 'line-color': '#9cadaa' };
    if (sourceLayer === 'transportation' || sourceLayer === 'aeroway') {
      const color = /rail/.test(layer.id) ? '#aab8b5' : /casing/.test(layer.id) ? '#cbd5ce'
        : /motorway|trunk|primary|secondary/.test(layer.id) ? '#f8f4e5' : '#fcfdf9';
      return { 'line-color': color };
    }
  }
  if (layer.type === 'symbol' && layer.layout?.['text-field']) return {
    'text-color': sourceLayer === 'water_name' || sourceLayer === 'waterway' ? '#4c7c80' : '#536d6b',
    'text-halo-color': '#f8fbf7', 'text-halo-width': 1.2,
  };
  return {};
}

/**
 * Optional Simulation satellite basemap (Esri World Imagery). Capture dates vary
 * by place; it is visual context only, never current conditions or verified
 * hospital entrances.
 */
export const SATELLITE_IMAGERY = {
  layerId: 'satellite-imagery',
  sourceId: 'satellite-imagery',
  tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
  tileSize: 256,
  maxzoom: 19,
  attribution: 'Imagery © Esri, Maxar, Earthstar Geographics, and the GIS User Community',
} as const;

/** Base-map lines that clutter imagery: minor roads, paths, rails, casings, tunnels and arrows. */
export function hiddenOverImagery(layer: LayerSpecification): boolean {
  const sourceLayer = 'source-layer' in layer ? layer['source-layer'] : '';
  if (sourceLayer === 'transportation')
    return /casing|minor|service|path|street|rail|hatching|arrow|area_pattern|^tunnel_/.test(layer.id);
  return sourceLayer === 'aeroway' || layer.id === 'park_outline';
}

/** Hybrid styling over imagery: light labels with dark halos, major roads highlighted. */
export function imageryLayerPaint(layer: LayerSpecification): Record<string, string | number> {
  const sourceLayer = 'source-layer' in layer ? layer['source-layer'] : '';
  if (layer.type === 'symbol' && layer.layout?.['text-field']) return {
    'text-color': sourceLayer === 'water_name' || sourceLayer === 'waterway' ? '#d4eff0' : '#ffffff',
    'text-halo-color': '#132b2a', 'text-halo-width': 1.4,
  };
  if (layer.type === 'line' && sourceLayer === 'transportation') {
    if (/motorway|trunk|primary/.test(layer.id)) return { 'line-color': '#f2c45a' };
    if (/secondary|tertiary/.test(layer.id)) return { 'line-color': '#f4f1e8' };
  }
  return dashboardLayerPaint(layer);
}

type BaseMap = Pick<MapLibreMap, 'getStyle' | 'getLayer' | 'getSource' | 'addSource' | 'addLayer' | 'setPaintProperty' | 'setLayoutProperty'>;

/** Adds the optional imagery under roads and labels (a hybrid view), hidden until chosen.
 *  Shared by Dashboard and Simulation; call on every `style.load`. */
export function addSatelliteImagery(map: BaseMap) {
  const { layerId, sourceId, ...imagery } = SATELLITE_IMAGERY;
  if (!map.getSource(sourceId)) map.addSource(sourceId, { type: 'raster', ...imagery, tiles: [...imagery.tiles] });
  const firstRoad = map.getStyle().layers.find(layer => 'source-layer' in layer && layer['source-layer'] === 'transportation')?.id;
  if (!map.getLayer(layerId)) map.addLayer({ id: SATELLITE_IMAGERY.layerId, type: 'raster', source: SATELLITE_IMAGERY.sourceId, layout: { visibility: 'none' }, paint: { 'raster-fade-duration': 150 } }, firstRoad);
}

/** Switches the provider's base layers between street context and imagery (app layers are
 *  untouched) and shows 3D or flat buildings. Flat footprints are redundant over imagery. */
export function applyBaseMap(map: BaseMap, satellite: boolean, buildings3d: boolean) {
  for (const layer of map.getStyle().layers) {
    if (!('source' in layer) || layer.source !== 'openmaptiles') continue;
    for (const [property, value] of Object.entries(satellite ? imageryLayerPaint(layer) : dashboardLayerPaint(layer))) map.setPaintProperty(layer.id, property, value);
    if (hiddenOverImagery(layer)) map.setLayoutProperty(layer.id, 'visibility', satellite ? 'none' : 'visible');
  }
  if (map.getLayer(SATELLITE_IMAGERY.layerId)) map.setLayoutProperty(SATELLITE_IMAGERY.layerId, 'visibility', satellite ? 'visible' : 'none');
  if (map.getLayer('building-3d')) map.setLayoutProperty('building-3d', 'visibility', buildings3d ? 'visible' : 'none');
  if (map.getLayer('building')) map.setLayoutProperty('building', 'visibility', buildings3d || satellite ? 'none' : 'visible');
}
