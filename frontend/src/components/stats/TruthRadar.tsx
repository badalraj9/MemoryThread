// Truth Score Radar Visualization

import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import type { Memory } from '../../api/types';

interface TruthRadarProps {
  memories: Memory[];
  width?: number;
  height?: number;
}

export function TruthRadar({ memories, width = 200, height = 200 }: TruthRadarProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || memories.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) / 2 - 20;

    // Metrics to display
    const metrics = [
      { key: 'truth', label: 'Truth', getValue: (m: Memory) => m.truth_score / 4 },
      { key: 'confidence', label: 'Confidence', getValue: (m: Memory) => m.confidence },
      { key: 'authority', label: 'Authority', getValue: (m: Memory) => m.authority },
    ];

    // Average values across all memories
    const avgValues = metrics.map(metric => ({
      ...metric,
      value: d3.mean(memories, metric.getValue) || 0,
    }));

    // Create scales
    const angleScale = d3.scaleLinear()
      .domain([0, metrics.length - 1])
      .range([0, 2 * Math.PI]);

    const radiusScale = d3.scaleLinear()
      .domain([0, 1])
      .range([0, radius]);

    // Draw circular grid
    const gridLevels = [0.25, 0.5, 0.75, 1];
    const gridGroup = svg.append('g').attr('class', 'grid');

    gridLevels.forEach(level => {
      const r = radiusScale(level);
      gridGroup.append('circle')
        .attr('cx', centerX)
        .attr('cy', centerY)
        .attr('r', r)
        .attr('fill', 'none')
        .attr('stroke', 'rgba(0, 248, 255, 0.1)')
        .attr('stroke-width', 1)
        .attr('stroke-dasharray', '3,3');
    });

    // Draw axis lines and labels
    avgValues.forEach((metric, i) => {
      const angle = angleScale(i) - Math.PI / 2;
      const x = centerX + radius * Math.cos(angle);
      const y = centerY + radius * Math.sin(angle);

      gridGroup.append('line')
        .attr('x1', centerX)
        .attr('y1', centerY)
        .attr('x2', x)
        .attr('y2', y)
        .attr('stroke', 'rgba(0, 248, 255, 0.15)')
        .attr('stroke-width', 1);

      // Labels
      const labelX = centerX + (radius + 15) * Math.cos(angle);
      const labelY = centerY + (radius + 15) * Math.sin(angle);
      
      gridGroup.append('text')
        .attr('x', labelX)
        .attr('y', labelY)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .attr('fill', '#556677')
        .attr('font-size', '8px')
        .attr('font-family', 'var(--font-mono)')
        .text(metric.label);
    });

    // Create area generator
    const lineGenerator = d3.lineRadial<typeof avgValues[0]>()
      .angle((_d, i) => angleScale(i))
      .radius((d) => radiusScale(d.value))
      .curve(d3.curveLinearClosed);

    // Draw the data area
    const dataGroup = svg.append('g').attr('class', 'data');

    // Gradient fill
    const gradient = svg.append('defs')
      .append('radialGradient')
      .attr('id', 'radar-gradient')
      .attr('cx', '50%')
      .attr('cy', '50%')
      .attr('r', '50%');

    gradient.append('stop')
      .attr('offset', '0%')
      .attr('stop-color', 'rgba(0, 248, 255, 0.3)');

    gradient.append('stop')
      .attr('offset', '100%')
      .attr('stop-color', 'rgba(136, 68, 255, 0.1)');

    dataGroup.append('path')
      .datum(avgValues)
      .attr('d', lineGenerator)
      .attr('fill', 'url(#radar-gradient)')
      .attr('stroke', '#00f0ff')
      .attr('stroke-width', 2)
      .attr('filter', 'drop-shadow(0 0 8px rgba(0, 248, 255, 0.5))');

    // Draw data points
    avgValues.forEach((metric, i) => {
      const angle = angleScale(i) - Math.PI / 2;
      const r = radiusScale(metric.value);
      const x = centerX + r * Math.cos(angle);
      const y = centerY + r * Math.sin(angle);

      dataGroup.append('circle')
        .attr('cx', x)
        .attr('cy', y)
        .attr('r', 4)
        .attr('fill', '#00f0ff')
        .attr('filter', 'drop-shadow(0 0 6px rgba(0, 248, 255, 0.8))');
    });

    // Center value text
    const avgTruth = d3.mean(memories, d => d.truth_score) || 0;
    svg.append('text')
      .attr('x', centerX)
      .attr('y', centerY + 4)
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('fill', '#00ff88')
      .attr('font-size', '16px')
      .attr('font-weight', '600')
      .attr('font-family', 'var(--font-mono)')
      .attr('filter', 'drop-shadow(0 0 4px rgba(0, 255, 136, 0.6))')
      .text(avgTruth.toFixed(2));

  }, [memories, width, height]);

  if (memories.length === 0) {
    return (
      <div className="flex items-center justify-center" style={{ width, height }}>
        <span className="text-[var(--color-text-tertiary)] text-xs">No data</span>
      </div>
    );
  }

  return (
    <svg 
      ref={svgRef} 
      width={width} 
      height={height}
      className="overflow-visible"
    />
  );
}