import React from 'react';
import { Handle, Position } from 'reactflow';
import './NodeStyles.css';

function SearchTermNode({ data }) {
  return (
    <div className="node search-term-node">
      <Handle type="target" position={Position.Top} />
      <div className="node-content">
        <div className="node-label">{data.label || data.term}</div>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

export default SearchTermNode;





