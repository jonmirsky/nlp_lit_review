import React, { useState } from 'react';
import { Handle, Position } from 'reactflow';
import PaperList from './PaperList';
import './NodeStyles.css';
import './OverlapGroupNode.css';

function DatabaseNode({ data }) {
  const [showPapers, setShowPapers] = useState(false);
  const isUncategorized = data.is_uncategorized || false;
  const isNlpExtraction = data.is_nlp_extraction || false;
  const papers = data.papers || [];
  const paperCount = data.paper_count || papers.length;

  const handleNodeClick = (e) => {
    if (isUncategorized) {
      e.stopPropagation();
      e.preventDefault();
      setShowPapers(!showPapers);
    }
  };

  const className = `node database-node ${isUncategorized ? `uncategorized-node clickable ${showPapers ? 'expanded' : ''}` : ''} ${isNlpExtraction ? 'nlp-extraction-node' : ''}`;

  return (
    <div 
      className={className}
      data-label={data.label}
      onMouseDown={isUncategorized ? (e) => e.stopPropagation() : undefined}
      title={isUncategorized ? 'Click header to toggle paper list' : undefined}
    >
      <Handle type="target" position={Position.Left} />
      <div className="node-content">
        <div 
          className="node-label"
          onClick={isUncategorized ? handleNodeClick : undefined}
          style={isUncategorized ? { cursor: 'pointer' } : undefined}
        >
          {data.label}
          {isUncategorized && <span className="paper-count"> ({paperCount} papers)</span>}
        </div>
        {isUncategorized && showPapers && (
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

export default DatabaseNode;
