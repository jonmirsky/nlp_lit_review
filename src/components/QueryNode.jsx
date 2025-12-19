import React, { useState } from 'react';
import { Handle, Position } from 'reactflow';
import './NodeStyles.css';

function QueryNode({ data }) {
  const queryString = data.query || data.query_string || '';
  // Check if this is the NLP_Extraction node (show full query)
  const isNlpExtraction = data.label && data.label.toUpperCase().includes('NLP');

  return (
    <div className={`node query-node ${isNlpExtraction ? 'nlp-query-node' : ''}`}>
      <Handle type="target" position={Position.Left} />
      <div className="node-content">
        <div className="node-label">{data.label}</div>
        {queryString && (
          <div className="query-preview">
            {queryString}
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

export default QueryNode;





