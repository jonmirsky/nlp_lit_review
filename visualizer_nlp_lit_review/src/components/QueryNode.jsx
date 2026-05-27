import React, { useState } from 'react';
import { Handle, Position } from 'reactflow';
import './NodeStyles.css';
import PaperList from './PaperList';

function QueryNode({ data }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const queryString = data.query || data.query_string || '';
  const papers = data.papers || [];
  const paperCount = data.paper_count !== undefined ? data.paper_count : papers.length;
  const hasDirectPapers = paperCount > 0;
  // Check if this is the NLP_Extraction node (show full query)
  const isNlpExtraction = data.label && data.label.toUpperCase().includes('NLP');

  return (
    <div
      className={`node query-node ${isNlpExtraction ? 'nlp-query-node' : ''} ${hasDirectPapers ? 'clickable expanded-query-node' : ''} ${isExpanded ? 'expanded' : ''}`}
      title={hasDirectPapers ? 'Click header to toggle paper list' : undefined}
    >
      <Handle type="target" position={Position.Left} />
      <div className="node-content">
        <div
          className="node-label"
          onClick={hasDirectPapers ? (e) => {
            e.stopPropagation();
            e.preventDefault();
            setIsExpanded(!isExpanded);
          } : undefined}
          style={hasDirectPapers ? { cursor: 'pointer' } : undefined}
        >
          {data.label}
          {hasDirectPapers && (
            <span className="paper-count"> ({paperCount} papers)</span>
          )}
        </div>
        {queryString && (
          <div className="query-preview">
            {queryString}
          </div>
        )}
        {hasDirectPapers && isExpanded && (
          <div
            className="papers-container nodrag"
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

export default QueryNode;












