/**
 * Cluster Map Web Component
 * 
 * Displays clusters in a radar/spider diagram visualization using ApexCharts.
 * Shows clusters positioned relative to workspace centroid (center).
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

        // Ensure the custom element itself has height to fill its parent
        this.style.display = 'block';
        this.style.width = '100%';
        this.style.height = '100%';

        // Create container for chart
        const container = document.createElement('div');
        container.id = `cluster-map-chart-${this.workspaceId}`;
        container.style.width = '100%';
        container.style.height = '100%';
        this.appendChild(container);

        // Load data and render chart
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

        // Prepare data for ApexCharts radar chart
        // Convert clusters to polar coordinates
        const clusters = this.data.clusters;
        const seriesData = clusters.map(cluster => {
            // Convert angle (degrees) to radians for positioning
            const angleRad = (cluster.position.angle * Math.PI) / 180;
            // Distance from center (alignment score)
            const distance = cluster.position.distance;
            
            // Convert polar to Cartesian for radar chart
            // ApexCharts radar uses labels around the circle
            // We'll use a scatter-like approach with custom positioning
            return {
                x: cluster.position.angle,
                y: cluster.position.distance,
                fillColor: this.getVelocityColor(cluster.velocity),
                size: Math.sqrt(cluster.size) * 2, // Size encoding
                meta: cluster
            };
        });

        // Create radar chart configuration
        const options = {
            chart: {
                type: 'radar',
                height: '100%',
                toolbar: { show: false },
                events: {
                    dataPointSelection: (event, chartContext, config) => {
                        const cluster = clusters[config.dataPointIndex];
                        if (cluster) {
                            this.showClusterDetail(cluster.id);
                        }
                    }
                }
            },
            series: [{
                name: 'Clusters',
                data: clusters.map((cluster, idx) => {
                    // For radar chart, we need to create a data point at each angle
                    // Create a simple representation: distance from center
                    return cluster.position.distance;
                })
            }],
            labels: clusters.map((cluster, idx) => `Cluster ${cluster.id}`),
            plotOptions: {
                radar: {
                    polygons: {
                        fill: {
                            colors: ['transparent']
                        },
                        strokeColors: ['#e0e0e0'],
                        connectorColors: ['#e0e0e0']
                    }
                }
            },
            markers: {
                size: clusters.map(cluster => Math.sqrt(cluster.size) * 3),
                colors: clusters.map(cluster => this.getVelocityColor(cluster.velocity)),
                strokeColors: clusters.map(cluster => this.getVelocityColor(cluster.velocity)),
                strokeWidth: 2,
                hover: {
                    size: 8
                }
            },
            tooltip: {
                custom: function({seriesIndex, dataPointIndex, w}) {
                    const cluster = clusters[dataPointIndex];
                    if (!cluster) return '';
                    return `
                        <div style="padding: 0.5rem;">
                            <strong>Cluster ${cluster.id}</strong><br/>
                            Size: ${cluster.size}<br/>
                            Alignment: ${cluster.alignment.toFixed(2)}<br/>
                            Velocity: ${cluster.velocity.toFixed(2)}<br/>
                            ${cluster.drift_distance !== null ? `Drift: ${cluster.drift_distance.toFixed(3)}<br/>` : ''}
                        </div>
                    `;
                }
            },
            xaxis: {
                categories: clusters.map((cluster, idx) => `Cluster ${cluster.id}`)
            },
            yaxis: {
                show: false,
                min: 0,
                max: 1
            },
            fill: {
                opacity: 0.3
            },
            stroke: {
                width: 2
            },
            colors: clusters.map(cluster => this.getVelocityColor(cluster.velocity))
        };

        // Initialize ApexCharts
        if (typeof ApexCharts !== 'undefined') {
            this.chart = new ApexCharts(container, options);
            this.chart.render();
        } else {
            console.error('ApexCharts is not loaded');
            this.showFallback();
        }
    }

    getVelocityColor(velocity) {
        // Color gradient: green (high velocity) to red (low velocity)
        if (velocity >= 0.7) return '#10b981'; // green-500
        if (velocity >= 0.4) return '#f59e0b'; // amber-500
        if (velocity >= 0.2) return '#f97316'; // orange-500
        return '#ef4444'; // red-500
    }

    showClusterDetail(clusterId) {
        // Trigger HTMX request to show cluster detail
        const event = new CustomEvent('showClusterDetail', {
            detail: { clusterId, workspaceId: this.workspaceId }
        });
        document.body.dispatchEvent(event);
        
        // Also try HTMX directly
        if (typeof htmx !== 'undefined') {
            htmx.ajax('GET', `/workspaces/${this.workspaceId}/clusters/${clusterId}/`, {
                target: '#dialog-body',
                swap: 'innerHTML'
            });
            const dialog = document.getElementById('resource-dialog');
            if (dialog) dialog.show();
        }
    }

    showEmptyState() {
        const container = document.getElementById(`cluster-map-chart-${this.workspaceId}`);
        if (container) {
            container.innerHTML = '<div style="padding: 2rem; text-align: center; color: var(--sl-color-neutral-500);">No clusters yet. Clusters will appear here as documents are processed.</div>';
        }
    }

    showFallback() {
        const fallback = document.getElementById('cluster-map-fallback');
        if (fallback) {
            fallback.style.display = 'block';
        }
    }
}

// Register the custom element
customElements.define('cluster-map', ClusterMap);
