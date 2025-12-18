import React, { useState } from 'react';
import { Handle, Position } from 'reactflow';
import PaperList from './PaperList';
import './NodeStyles.css';
import './OverlapGroupNode.css';

function DatabaseNode({ data }) {
  const [showPapers, setShowPapers] = useState(false);
  const isUncategorized = data.is_uncategorized || false;
  const papers = data.papers || [];
  const paperCount = data.paper_count || papers.length;

  const handleLabelClick = (e) => {
    if (isUncategorized) {
      e.stopPropagation();
      e.preventDefault();
      setShowPapers(!showPapers);
    }
  };

  return (
    <div className={`node database-node ${isUncategorized ? 'uncategorized-node' : ''}`}>
      <Handle type="target" position={Position.Top} />
      <div className="node-content">
        <div 
          className={`node-label ${isUncategorized ? 'clickable' : ''}`}
          onClick={isUncategorized ? handleLabelClick : undefined}
          onMouseDown={isUncategorized ? (e) => e.stopPropagation() : undefined}
          title={isUncategorized ? 'Click to toggle paper list' : undefined}
        >
          {data.label}
          {isUncategorized && <span className="paper-count"> ({paperCount} papers)</span>}
        </div>
        {isUncategorized && showPapers && (
          <div className="papers-container" onMouseDown={(e) => e.stopPropagation()}>
            <PaperList papers={papers} />
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

export default DatabaseNode;




