import React, { useState } from 'react';
import { Handle, Position } from 'reactflow';
import './NodeStyles.css';

function QueryNode({ data }) {
  const [showFullQuery, setShowFullQuery] = useState(false);
  const queryString = data.query || data.query_string || '';
  // Create a preview by truncating the query to first 100 characters
  const displayQuery = data.display_query || (queryString ? queryString.substring(0, 100) + '...' : data.label || 'Query');

  return (
    <div className="node query-node">
      <Handle type="target" position={Position.Top} />
      <div className="node-content">
        <div className="node-label">{data.label}</div>
        {queryString && (
          <div 
            className="query-preview clickable"
            onClick={() => setShowFullQuery(!showFullQuery)}
            title="Click to toggle full query"
          >
            {showFullQuery ? queryString : displayQuery}
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

export default QueryNode;




