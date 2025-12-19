import React from 'react';
import { Handle, Position } from 'reactflow';
import './NodeStyles.css';

function CommonTermsNode({ data }) {
  return (
    <div className="node common-terms-node">
      <Handle type="target" position={Position.Top} />
      <div className="node-content">
        <div className="node-label">{data.label || 'Common Terms'}</div>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

export default CommonTermsNode;





