import React, { useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Polyline, Popup, useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';

const icon = new L.DivIcon({ className: 'map-pin', html: '<span></span>', iconSize: [22, 22], iconAnchor: [11, 22] });
const dropIcon = new L.DivIcon({ className: 'map-pin drop', html: '<span></span>', iconSize: [22, 22], iconAnchor: [11, 22] });

function Fit({ points }) {
  const map = useMap();
  useEffect(() => {
    const valid = (points || []).filter(p => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1]));
    // Deterministic, non-animated framing: closing a map modal mid-animation can leave a Leaflet
    // position frame referencing a removed pane (_leaflet_pos). Demo/navigation flows unmount maps often.
    if (valid.length === 1) map.setView(valid[0], 14, { animate: false });
    else if (valid.length > 1) map.fitBounds(valid, { padding: [35, 35], maxZoom: 14, animate: false });
  }, [JSON.stringify(points), map]);
  return null;
}
function Click({ onPick }) {
  useMapEvents({ click(e) { onPick?.({ id: `pin-${Date.now()}`, name: `Pinned location (${e.latlng.lat.toFixed(4)}, ${e.latlng.lng.toFixed(4)})`, lat: e.latlng.lat, lng: e.latlng.lng, subtitle: 'Map pin' }); } });
  return null;
}
export default function MapView({ pickup, drop, points = [], route, markers = [], onPick, height = 300 }) {
  const all = [...points, ...(pickup ? [[pickup.lat, pickup.lng]] : []), ...(drop ? [[drop.lat, drop.lng]] : []), ...markers.map(m => [m.lat, m.lng])];
  const center = all[0] || [26.9124, 75.7873];
  return <div className="map-view" style={{ height }}>
    <MapContainer center={center} zoom={12} scrollWheelZoom={false} style={{ height: '100%', width: '100%' }}>
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
      <Fit points={all.length ? all : [center]} /><Click onPick={onPick} />
      {pickup && <Marker position={[pickup.lat, pickup.lng]} icon={icon}><Popup>Pickup: {pickup.name}</Popup></Marker>}
      {drop && <Marker position={[drop.lat, drop.lng]} icon={dropIcon}><Popup>Drop-off: {drop.name}</Popup></Marker>}
      {markers.map((m, i) => <Marker key={i} position={[m.lat, m.lng]} icon={icon}><Popup>{m.label || m.vehicle_type || `Stop ${i + 1}`}</Popup></Marker>)}
      {route?.length > 1 && <Polyline positions={route} pathOptions={{ color: '#17456b', weight: 4, opacity: .8 }} />}
      {points.length > 1 && !route && <Polyline positions={points} pathOptions={{ color: '#2e7d5b', weight: 3, dashArray: '6 6' }} />}
    </MapContainer>
  </div>;
}
