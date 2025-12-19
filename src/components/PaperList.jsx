import React, { useState, useMemo, useRef, useEffect } from 'react';
import { FixedSizeList as List } from 'react-window';
import './PaperList.css';

function PaperList({ papers }) {
  const [sortBy, setSortBy] = useState('year'); // 'year' or 'title'
  const [searchQuery, setSearchQuery] = useState('');
  const [sortOrder, setSortOrder] = useState('desc'); // 'asc' or 'desc'
  const listContainerRef = useRef(null);

  // Filter and sort papers
  const filteredAndSortedPapers = useMemo(() => {
    let filtered = papers;

    // Filter by search query
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = papers.filter(
        (paper) =>
          (paper.title && paper.title.toLowerCase().includes(query)) ||
          (paper.abstract && paper.abstract.toLowerCase().includes(query))
      );
    }

    // Sort
    const sorted = [...filtered].sort((a, b) => {
      let comparison = 0;

      if (sortBy === 'year') {
        const yearA = a.year || 0;
        const yearB = b.year || 0;
        comparison = yearA - yearB;
      } else if (sortBy === 'title') {
        const titleA = (a.title || '').toLowerCase();
        const titleB = (b.title || '').toLowerCase();
        comparison = titleA.localeCompare(titleB);
      }

      return sortOrder === 'asc' ? comparison : -comparison;
    });

    return sorted;
  }, [papers, searchQuery, sortBy, sortOrder]);

  // Ensure wheel events work for scrolling when hovering over paper list
  // React Flow's noWheelClassName should handle this, but we add a safety handler
  useEffect(() => {
    const container = listContainerRef.current;
    if (!container) return;

    const handleWheel = (e) => {
      // Only stop propagation if the event target is within the scrollable list area
      // This allows scrolling in the list while preserving React Flow zoom elsewhere
      const target = e.target;
      const isInScrollableArea = container.querySelector('.paper-list')?.contains(target) ||
                                 container.querySelector('[class*="react-window"]')?.contains(target);
      
      if (isInScrollableArea) {
        // Stop propagation to prevent React Flow from capturing wheel events
        // This allows two-finger scrolling to work in the paper list
        e.stopPropagation();
      }
      // If not in scrollable area, let React Flow handle it for zooming
    };

    // Add wheel event listener
    container.addEventListener('wheel', handleWheel, { passive: false });
    
    return () => {
      container.removeEventListener('wheel', handleWheel);
    };
  }, []);

  const handleDoubleClick = async (paper) => {
    if (!paper.id) {
      alert('Paper ID not available');
      return;
    }

    // Check if PDF is available
    try {
      const response = await fetch(`/api/pdf/check/${paper.id}`);
      const data = await response.json();

      if (data.available) {
        // Open PDF in new tab
        const pdfUrl = `/api/pdf/${paper.id}`;
        window.open(pdfUrl, '_blank', 'noopener,noreferrer');
        // Note: If popup is blocked, browser will show its own indicator
        // User can right-click paper and select "Open in new tab" as workaround
      } else {
        alert('PDF not available: ' + (data.error || 'File not found'));
      }
    } catch (error) {
      console.error('Error checking PDF:', error);
      // Try to open in new tab anyway
      const pdfUrl = `/api/pdf/${paper.id}`;
      window.open(pdfUrl, '_blank', 'noopener,noreferrer');
    }
  };

  const PaperRow = ({ index, style }) => {
    const paper = filteredAndSortedPapers[index];
    const hasPdf = paper.pdf_path && paper.pdf_path.trim() !== '';

    return (
      <div
        style={style}
        className={`paper-row ${hasPdf ? 'has-pdf' : 'no-pdf'}`}
        onDoubleClick={() => handleDoubleClick(paper)}
        title={hasPdf ? 'Double-click to open PDF' : 'PDF not available'}
      >
        <div className="paper-title">{paper.title || 'Untitled'}</div>
        <div className="paper-year">{paper.year || 'No year'}</div>
        {!hasPdf && <span className="no-pdf-indicator">⚠️</span>}
      </div>
    );
  };

  return (
    <div className="paper-list-container">
      <div className="paper-list-controls">
        <input
          type="text"
          placeholder="Search in title/abstract..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="search-input"
        />
        <div className="sort-controls">
          <label>
            Sort by:
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="sort-select"
            >
              <option value="year">Year</option>
              <option value="title">Title</option>
            </select>
          </label>
          <label>
            Order:
            <select
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value)}
              className="sort-select"
            >
              <option value="desc">Descending</option>
              <option value="asc">Ascending</option>
            </select>
          </label>
        </div>
        <div className="paper-count">
          Showing {filteredAndSortedPapers.length} of {papers.length} papers
        </div>
      </div>
      <div className="paper-list nowheel" ref={listContainerRef}>
            {filteredAndSortedPapers.length > 0 ? (
              <List
                height={300}
                itemCount={filteredAndSortedPapers.length}
                itemSize={80}
                width="100%"
                className="nowheel"
              >
                {PaperRow}
              </List>
            ) : (
              <div className="no-papers">No papers found</div>
            )}
      </div>
    </div>
  );
}

export default PaperList;





