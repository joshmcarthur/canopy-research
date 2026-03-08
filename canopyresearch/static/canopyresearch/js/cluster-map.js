/**
 * Cluster Map Web Component
 *
 * Displays clusters as a 2D scatter plot using ApexCharts.
 * Cluster centroids are projected to 2D via PCA on the server side.
 * Bubble size encodes cluster size; colour encodes velocity.
 */

class ClusterMap extends HTMLElement {
    constructor() {
        super();
        this.workspaceId = null;
        this.chart = null;
        this.data = null;
    }

    connectedCallback() {
        this.workspaceId = this.getAttribute('workspace-id');
        if (!this.workspaceId) {
            console.error('cluster-map: workspace-id attribute is required');
            return;
        }

        this.style.display = 'block';
        this.style.width = '100%';
        this.style.height = '100%';

        const container = document.createElement('div');
        container.id = `cluster-map-chart-${this.workspaceId}`;
        container.style.width = '100%';
        container.style.height = '100%';
        this.appendChild(container);

        this.loadData();
    }

    async loadData() {
        try {
            const response = await fetch(`/workspaces/${this.workspaceId}/clusters/map.json`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            this.data = await response.json();
            this.renderChart();
        } catch (error) {
            console.error('Failed to load cluster map data:', error);
            this.showFallback();
        }
    }

    renderChart() {
        if (!this.data || !this.data.clusters || this.data.clusters.length === 0) {
            this.showEmptyState();
            return;
        }

        const containerId = `cluster-map-chart-${this.workspaceId}`;
        const container = document.getElementById(containerId);
        if (!container) {
            console.error('Chart container not found');
            return;
        }

        const clusters = this.data.clusters;

        // Build one series per cluster so each bubble gets its own colour and tooltip
        const series = clusters.map(cluster => ({
            name: cluster.label || `Cluster ${cluster.id}`,
            data: [{
                x: cluster.position.x,
                y: cluster.position.y,
                // z drives bubble size — sqrt to keep large clusters from overwhelming small ones
                z: Math.max(Math.sqrt(cluster.size) * 4, 4),
            }],
        }));

        const options = {
            chart: {
                type: 'bubble',
                height: '100%',
                toolbar: { show: false },
                zoom: { enabled: false },
                events: {
                    dataPointSelection: (event, chartContext, config) => {
                        const cluster = clusters[config.seriesIndex];
                        if (cluster) {
                            this.showClusterDetail(cluster.id);
                        }
                    },
                },
            },
            series,
            colors: clusters.map(c => this.velocityColor(c.velocity)),
            dataLabels: { enabled: false },
            xaxis: {
                tickAmount: 5,
                labels: { show: false },
                axisBorder: { show: false },
                axisTicks: { show: false },
                title: { text: '' },
            },
            yaxis: {
                tickAmount: 5,
                labels: { show: false },
                title: { text: '' },
            },
            grid: {
                borderColor: 'var(--sl-color-neutral-200)',
                xaxis: { lines: { show: true } },
                yaxis: { lines: { show: true } },
            },
            legend: {
                show: clusters.length <= 12,
                position: 'bottom',
                fontSize: '12px',
            },
            tooltip: {
                custom: ({ seriesIndex }) => {
                    const c = clusters[seriesIndex];
                    if (!c) return '';
                    const label = c.label ? `<strong>${c.label}</strong><br/>` : `<strong>Cluster ${c.id}</strong><br/>`;
                    const drift = c.drift_distance !== null ? `Drift: ${c.drift_distance.toFixed(3)}<br/>` : '';
                    return `<div style="padding:0.5rem;font-size:0.85rem;">
                        ${label}
                        Size: ${c.size}<br/>
                        Alignment: ${c.alignment.toFixed(2)}<br/>
                        Velocity: ${c.velocity.toFixed(2)}<br/>
                        ${drift}
                        <em style="font-size:0.75rem;color:#888;">Click to view details</em>
                    </div>`;
                },
            },
            fill: { opacity: 0.75 },
        };

        if (typeof ApexCharts !== 'undefined') {
            this.chart = new ApexCharts(container, options);
            this.chart.render();
        } else {
            console.error('ApexCharts is not loaded');
            this.showFallback();
        }
    }

    velocityColor(velocity) {
        if (velocity >= 0.7) return '#10b981'; // green
        if (velocity >= 0.4) return '#f59e0b'; // amber
        if (velocity >= 0.2) return '#f97316'; // orange
        return '#ef4444';                       // red
    }

    showClusterDetail(clusterId) {
        if (typeof htmx !== 'undefined') {
            htmx.ajax('GET', `/workspaces/${this.workspaceId}/clusters/${clusterId}/`, {
                target: '#dialog-body',
                swap: 'innerHTML',
            });
            const dialog = document.getElementById('resource-dialog');
            if (dialog) dialog.show();
        }
    }

    showEmptyState() {
        const container = document.getElementById(`cluster-map-chart-${this.workspaceId}`);
        if (container) {
            container.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--sl-color-neutral-500);">No clusters yet. Clusters will appear here as documents are processed.</div>';
        }
    }

    showFallback() {
        const fallback = document.getElementById('cluster-map-fallback');
        if (fallback) {
            fallback.style.display = 'block';
        }
    }
}

customElements.define('cluster-map', ClusterMap);
