async function initMap(logs) {
  const container = document.getElementById('visitor-map');
  const width = container.clientWidth || 800;
  const height = Math.round(width * 0.5);

  const svg = d3.select('#visitor-map')
    .append('svg')
    .attr('viewBox', `0 0 ${width} ${height}`)
    .attr('preserveAspectRatio', 'xMidYMid meet')
    .style('cursor', 'grab');

  const g = svg.append('g');

  const projection = d3.geoNaturalEarth1()
    .scale(width / 6.3)
    .translate([width / 2, height / 2]);

  const path = d3.geoPath().projection(projection);

  const world = await d3.json('https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json');
  const countries = topojson.feature(world, world.objects.countries);

  g.append('g')
    .selectAll('path')
    .data(countries.features)
    .join('path')
    .attr('d', path)
    .attr('fill', '#d4e9f7')
    .attr('stroke', '#aaa')
    .attr('stroke-width', 0.5);

  const located = logs.filter(l => l.location?.lat != null && l.location?.lon != null);

  g.selectAll('circle')
    .data(located)
    .join('circle')
    .attr('cx', d => projection([d.location.lon, d.location.lat])[0])
    .attr('cy', d => projection([d.location.lon, d.location.lat])[1])
    .attr('r', 5)
    .append('title')
    .text(d => {
      const label = [d.location.city, d.location.country].filter(Boolean).join(', ');
      return `${label}\n${new Date(d.timestamp).toLocaleString()}`;
    });

  const zoom = d3.zoom()
    .scaleExtent([1, 12])
    .on('zoom', e => {
      g.attr('transform', e.transform);
      svg.style('cursor', e.transform.k > 1 ? 'grabbing' : 'grab');
    });

  svg.call(zoom);
}

async function genarateMapAndTable() {
  try {
    const response = await fetch('/api/fast_api_requests?order=timestamp.desc&limit=50');
    const data = await response.json();
    if (!Array.isArray(data)) {
      throw new Error(`Unexpected response: ${JSON.stringify(data)}`);
    }
    initTable(data);
    await initMap(data);
  } catch (error) {
    console.error('Error fetching logs:', error);
    document.getElementById('logs-container').innerHTML = '<p>Error loading logs</p>';
  }
}

function initTable(logs) {
  const container = document.getElementById('logs-container');
  if (!logs || logs.length === 0) {
    container.innerHTML = '<p>No logs found</p>';
    return;
  }

  let html = '<table class="logs-table"><thead><tr>';
  html += '<th>Timestamp</th><th>Method</th><th>Path</th><th>IP</th><th>User-Agent</th><th>Country</th><th>City</th>';
  html += '</tr></thead><tbody>';

  logs.forEach(log => {
    const timestamp = new Date(log.timestamp).toLocaleString();
    const userAgent = log.headers?.['user-agent'] || '—';
    const country = log.location?.country || '—';
    const city = log.location?.city || '—';

    html += `<tr>
      <td>${timestamp}</td>
      <td>${log.method}</td>
      <td>${log.path}</td>
      <td><span class="redacted" title="IP redacted">████</span></td>
      <td>${userAgent}</td>
      <td>${country}</td>
      <td>${city}</td>
    </tr>`;
  });

  html += '</tbody></table>';
  container.innerHTML = html;
}

document.addEventListener('DOMContentLoaded', genarateMapAndTable);
