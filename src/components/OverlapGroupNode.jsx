import React, { useState } from 'react';
import { Handle, Position } from 'reactflow';
import PaperList from './PaperList';
import './NodeStyles.css';
import './OverlapGroupNode.css';

function OverlapGroupNode({ data }) {
  const [showPapers, setShowPapers] = useState(false);
  const papers = data.papers || [];
  const paperCount = data.paper_count !== undefined ? data.paper_count : papers.length;
  const isMostCitedAggregate = data.is_most_cited_aggregate || false;
  const isMostRelevantAggregate = data.is_most_relevant_aggregate || false;

  const handleLabelClick = (e) => {
    e.stopPropagation(); // Prevent React Flow from handling the click
    e.preventDefault(); // Prevent any default behavior
    setShowPapers(!showPapers);
  };

  // Determine which CSS class to apply
  let aggregateClass = '';
  if (isMostCitedAggregate) {
    aggregateClass = 'most-cited-aggregate-node';
  } else if (isMostRelevantAggregate) {
    aggregateClass = 'most-relevant-aggregate-node';
  }

  return (
    <div className={`node overlap-group-node ${aggregateClass}`}>
      <Handle type="target" position={Position.Top} />
      <div className="node-content">
        <div 
          className="node-label clickable"
          onClick={handleLabelClick}
          onMouseDown={(e) => e.stopPropagation()} // Prevent node dragging when clicking label
          title="Click to toggle paper list"
        >
          {data.label}
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

export default OverlapGroupNode;




