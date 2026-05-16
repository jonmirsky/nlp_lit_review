import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactFlow, {
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  ReactFlowProvider,
} from 'reactflow';
import 'reactflow/dist/style.css';
import DatabaseNode from './DatabaseNode';
import QueryNode from './QueryNode';
import BranchTermNode from './BranchTermNode';
import OverlapGroupNode from './OverlapGroupNode';
import WaypointEdge from './WaypointEdge';
import './FlowChart.css';

const nodeTypes = {
  database: DatabaseNode,
  query: QueryNode,
  branchTerm: BranchTermNode,
  overlapGroup: OverlapGroupNode,
};

const edgeTypes = {
  waypoint: WaypointEdge,
};

function FlowChartInner({ data }) {
  const [nodes, setNodes, onNodesChange] = useNodesState(data.nodes || []);
  const [edges, setEdges, onEdgesChange] = useEdgesState(data.edges || []);
  const wrapperRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0, scrollLeft: 0, scrollTop: 0 });

  const onConnect = useCallback(
    (params) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  // Check if the click target is a node or edge (should not trigger drag)
  const isNodeOrEdge = (target) => {
    // Check if target or any parent is a React Flow node or edge
    let element = target;
    while (element && element !== wrapperRef.current) {
      if (
        element.classList?.contains('react-flow__node') ||
        element.classList?.contains('react-flow__edge') ||
        element.closest?.('.react-flow__node') ||
        element.closest?.('.react-flow__edge')
      ) {
        return true;
      }
      element = element.parentElement;
    }
    return false;
  };

  // Handle mouse down - start drag if on white space
  const handleMouseDown = useCallback((e) => {
    // Only start drag on left mouse button and if not clicking on a node/edge
    if (e.button !== 0 || isNodeOrEdge(e.target)) {
      return;
    }

    const wrapper = wrapperRef.current;
    if (!wrapper) return;

    setIsDragging(true);
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      scrollLeft: wrapper.scrollLeft,
      scrollTop: wrapper.scrollTop,
    };

    // Prevent text selection during drag
    e.preventDefault();
  }, []);

  // Handle mouse move - update scroll position
  const handleMouseMove = useCallback((e) => {
    if (!isDragging || !wrapperRef.current) return;

    const wrapper = wrapperRef.current;
    const dx = e.clientX - dragStartRef.current.x;
    const dy = e.clientY - dragStartRef.current.y;

    wrapper.scrollLeft = dragStartRef.current.scrollLeft - dx;
    wrapper.scrollTop = dragStartRef.current.scrollTop - dy;

    e.preventDefault();
  }, [isDragging]);

  // Handle mouse up - end drag
  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Add global mouse event listeners for drag
  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      // Prevent text selection during drag
      document.body.style.userSelect = 'none';
      document.body.style.cursor = 'grabbing';

      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
        document.body.style.userSelect = '';
        document.body.style.cursor = '';
      };
    }
  }, [isDragging, handleMouseMove, handleMouseUp]);

  // Handle arrow key scrolling
  const handleKeyDown = useCallback((e) => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;

    // Only handle arrow keys if not typing in an input/textarea
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
      return;
    }

    const scrollAmount = 50; // pixels to scroll per keypress
    
    switch (e.key) {
      case 'ArrowUp':
        e.preventDefault();
        wrapper.scrollTop -= scrollAmount;
        break;
      case 'ArrowDown':
        e.preventDefault();
        wrapper.scrollTop += scrollAmount;
        break;
      case 'ArrowLeft':
        e.preventDefault();
        wrapper.scrollLeft -= scrollAmount;
        break;
      case 'ArrowRight':
        e.preventDefault();
        wrapper.scrollLeft += scrollAmount;
        break;
    }
  }, []);

  // Add keyboard event listener for arrow keys
  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleKeyDown]);

  // Update nodes and edges when data changes
  useEffect(() => {
    if (data.nodes) {
      setNodes(data.nodes);
    }
    if (data.edges) {
      setEdges(data.edges);
    }
  }, [data, setNodes, setEdges]);

  // Helper function to estimate node height based on label (matches Python logic)
  const estimateNodeHeight = (label, isNlpExtraction = false) => {
    if (!label) return isNlpExtraction ? 160 : 80;
    const baseNodeHeight = 80;
    const charsPerLine = 25;
    const lineHeight = 25;
    const lines = Math.max(1, Math.ceil(label.length / charsPerLine));
    let height = baseNodeHeight + (lines - 1) * lineHeight;
    // NLP_Extraction node is 60% taller
    if (isNlpExtraction) {
      height = height * 1.6;
    }
    return height;
  };

  // Calculate content bounds from nodes with padding (optimized - only recalculate when nodes change)
  const contentBounds = useMemo(() => {
    if (!nodes || nodes.length === 0) {
      return { width: 1500, height: 2000, offsetX: 0, offsetY: 0 };
    }
    
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;
    
    // Optimize: only iterate once, cache height calculations
    for (let i = 0; i < nodes.length; i++) {
      const node = nodes[i];
      const x = node.position?.x || 0;
      const y = node.position?.y || 0;
      const label = node.data?.label || '';
      const isNlpExtraction = node.data?.is_nlp_extraction || false;
      const isNlpQuery = label && label.toUpperCase().includes('NLP') && label.toUpperCase().includes('EXTRACTION');
      const nodeHeight = estimateNodeHeight(label, isNlpExtraction || isNlpQuery);
      const nodeWidth = isNlpQuery ? 350 : 250; // NLP query nodes are wider
      
      if (x < minX) minX = x;
      if (x + nodeWidth > maxX) maxX = x + nodeWidth;
      if (y < minY) minY = y;
      if (y + nodeHeight > maxY) maxY = y + nodeHeight;
    }
    
    // Add padding (2% on each side for top/left)
    const baseWidth = (maxX - minX) * 1.04;
    const baseHeight = (maxY - minY) * 1.04;
    // Add extra bottom padding (500px) to allow nodes to expand fully
    const expandedNodeHeight = 500; // Space for expanded node papers container (400px) + margin
    // Add extra right padding (300px) to allow rightmost nodes to expand fully
    const expandedNodeWidth = 300; // Space for expanded node papers container width
    const width = baseWidth + expandedNodeWidth;
    const height = baseHeight + expandedNodeHeight;
    
    return { 
      width: Math.max(width, 1500), 
      height: height,
      offsetX: minX - (maxX - minX) * 0.02,
      offsetY: minY - (maxY - minY) * 0.02
    };
  }, [nodes]);

  return (
    <div 
      ref={wrapperRef}
      className="flowchart-wrapper"
      onMouseDown={handleMouseDown}
      style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
    >
      <div 
        className="flowchart-container"
        style={{ 
          width: `${contentBounds.width}px`, 
          height: `${contentBounds.height}px` 
        }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          nodesDraggable={false}
          defaultViewport={{ 
            x: -contentBounds.offsetX + 50, 
            y: -contentBounds.offsetY + 50, 
            zoom: 1 
          }}
          attributionPosition="bottom-left"
          zoomOnScroll={false}
          zoomOnDoubleClick={false}
          panOnDrag={false}
          panOnScroll={false}
          preventScrolling={false}
          minZoom={1}
          maxZoom={1}
        >
          <Background />
        </ReactFlow>
      </div>
    </div>
  );
}

function FlowChart({ data }) {
  return (
    <ReactFlowProvider>
      <FlowChartInner data={data} />
    </ReactFlowProvider>
  );
}

export default FlowChart;





