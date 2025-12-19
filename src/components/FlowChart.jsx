import React, { useCallback, useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
} from 'reactflow';
import 'reactflow/dist/style.css';
import DatabaseNode from './DatabaseNode';
import QueryNode from './QueryNode';
import BranchTermNode from './BranchTermNode';
import OverlapGroupNode from './OverlapGroupNode';
import './FlowChart.css';

const nodeTypes = {
  database: DatabaseNode,
  query: QueryNode,
  branchTerm: BranchTermNode,
  overlapGroup: OverlapGroupNode,
};

function FlowChart({ data }) {
  const [nodes, setNodes, onNodesChange] = useNodesState(data.nodes || []);
  const [edges, setEdges, onEdgesChange] = useEdgesState(data.edges || []);

  const onConnect = useCallback(
    (params) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  // Update nodes and edges when data changes
  React.useEffect(() => {
    if (data.nodes) {
      setNodes(data.nodes);
    }
    if (data.edges) {
      setEdges(data.edges);
    }
  }, [data, setNodes, setEdges]);

  return (
    <div className="flowchart-container">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        nodeTypes={nodeTypes}
        fitView
        attributionPosition="bottom-left"
        noWheelClassName="nowheel"
        zoomOnScroll={true}
        minZoom={0.1}
        maxZoom={4}
      >
        <Background />
        <Controls />
        <MiniMap />
      </ReactFlow>
    </div>
  );
}

export default FlowChart;





