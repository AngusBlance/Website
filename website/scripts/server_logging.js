async function initMap(visitors) {
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

  const located = visitors.filter(v => v.lat != null && v.lon != null);

  g.selectAll('circle')
    .data(located)
    .join('circle')
    .attr('cx', d => projection([d.lon, d.lat])[0])
    .attr('cy', d => projection([d.lon, d.lat])[1])
    .attr('r', 5)
    .append('title')
    .text(d => {
      const label = [d.city, d.country].filter(Boolean).join(', ');
      return `${label}\n${d.visits} visit${d.visits !== 1 ? 's' : ''}`;
    });

  const zoom = d3.zoom()
    .scaleExtent([1, 12])
    .on('zoom', e => {
      g.attr('transform', e.transform);
      svg.style('cursor', e.transform.k > 1 ? 'grabbing' : 'grab');
    });

  svg.call(zoom);
}

// User agents come straight from request headers, so escape them before
// putting them into the page.
function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function genarateMapAndTable() {
  try {
    // The server groups visitors by IP itself and never sends the IPs.
    const response = await fetch('/api/visitors');
    const visitors = await response.json();
    if (!Array.isArray(visitors)) {
      throw new Error(`Unexpected response: ${JSON.stringify(visitors)}`);
    }
    initTable(visitors);
    await initMap(visitors);
  } catch (error) {
    console.error('Error fetching logs:', error);
    document.getElementById('logs-container').innerHTML = '<p>Error loading logs</p>';
  }
}

function initTable(visitors) {
  const container = document.getElementById('logs-container');
  if (!visitors || visitors.length === 0) {
    container.innerHTML = '<p>No visitors found</p>';
    return;
  }

  let html = '<table class="logs-table"><thead><tr>';
  html += '<th>IP</th><th>Visits</th><th>First Seen</th><th>Last Seen</th><th>Country</th><th>City</th><th>Browser</th>';
  html += '</tr></thead><tbody>';

  visitors.forEach((v, i) => {
    html += `<tr>
      <td><span class="redacted" title="IP redacted">████████</span></td>
      <td>${v.visits}</td>
      <td>${new Date(v.firstSeen).toLocaleString()}</td>
      <td>${new Date(v.lastSeen).toLocaleString()}</td>
      <td>${escapeHtml(v.country)}</td>
      <td>${escapeHtml(v.city)}</td>
      <td>${escapeHtml(v.userAgent)}</td>
    </tr>`;
  });

  html += '</tbody></table>';
  container.innerHTML = html;
}

document.addEventListener('DOMContentLoaded', genarateMapAndTable);
