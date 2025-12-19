import React, { useState } from 'react';
import { Handle, Position } from 'reactflow';
import PaperList from './PaperList';
import './NodeStyles.css';
import './OverlapGroupNode.css';

function BranchTermNode({ data }) {
  const [showPapers, setShowPapers] = useState(false);
  const papers = data.papers || [];
  const paperCount = data.paper_count || papers.length;

  const handleNodeClick = (e) => {
    e.stopPropagation();
    setShowPapers(!showPapers);
  };

  return (
    <div 
      className={`node branch-term-node clickable ${showPapers ? 'expanded' : ''}`}
      onMouseDown={(e) => e.stopPropagation()}
      title="Click header to toggle paper list"
    >
      <Handle type="target" position={Position.Left} />
      <div className="node-content">
        <div 
          className="node-label"
          onClick={handleNodeClick}
          style={{ cursor: 'pointer' }}
        >
          {data.label || data.branch_term}
          <span className="paper-count"> ({paperCount} papers)</span>
        </div>
        {showPapers && (
          <div 
            className="papers-container" 
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => e.stopPropagation()}
          >
            <PaperList papers={papers} />
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

export default BranchTermNode;





