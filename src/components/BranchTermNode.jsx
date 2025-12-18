import React, { useState } from 'react';
import { Handle, Position } from 'reactflow';
import PaperList from './PaperList';
import './NodeStyles.css';
import './OverlapGroupNode.css';

function BranchTermNode({ data }) {
  const [showPapers, setShowPapers] = useState(false);
  const papers = data.papers || [];
  const paperCount = data.paper_count || papers.length;

  const handleLabelClick = (e) => {
    e.stopPropagation(); // Prevent React Flow from handling the click
    setShowPapers(!showPapers);
  };

  return (
    <div className="node branch-term-node">
      <Handle type="target" position={Position.Top} />
      <div className="node-content">
        <div 
          className="node-label clickable"
          onClick={handleLabelClick}
          onMouseDown={(e) => e.stopPropagation()} // Prevent node dragging when clicking label
          title="Click to toggle paper list"
        >
          {data.label || data.branch_term}
          <span className="paper-count"> ({paperCount} papers)</span>
        </div>
        {showPapers && (
          <div className="papers-container" onMouseDown={(e) => e.stopPropagation()}>
            <PaperList papers={papers} />
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

export default BranchTermNode;




