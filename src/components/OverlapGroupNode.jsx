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

  const handleNodeClick = (e) => {
    e.stopPropagation();
    e.preventDefault();
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
    <div 
      className={`node overlap-group-node ${aggregateClass} clickable ${showPapers ? 'expanded' : ''}`}
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
          {data.label}
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

export default OverlapGroupNode;
