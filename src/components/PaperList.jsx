import React, { useState, useMemo, useRef, useEffect } from 'react';
import { FixedSizeList as List } from 'react-window';
import './PaperList.css';

function PaperList({ papers }) {
  const [sortBy, setSortBy] = useState('year'); // 'year' or 'title'
  const [searchQuery, setSearchQuery] = useState('');
  const [sortOrder, setSortOrder] = useState('desc'); // 'asc' or 'desc'
  const listContainerRef = useRef(null);

  // Right-click context menu state. `menu` is null when closed; otherwise
  // {x, y, paper, view} where view ∈ {'root', 'searchTerms'}.
  const [menu, setMenu] = useState(null);

  const closeMenu = () => setMenu(null);
  const handlePaperContextMenu = (e, paper) => {
    e.preventDefault();
    e.stopPropagation();
    setMenu({ x: e.clientX, y: e.clientY, paper, view: 'root' });
  };

  // Close menu on outside click or Escape.
  useEffect(() => {
    if (!menu) return undefined;
    const onDocClick = () => closeMenu();
    const onKey = (e) => {
      if (e.key === 'Escape') closeMenu();
    };
    document.addEventListener('click', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('click', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [menu]);

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
        onContextMenu={(e) => handlePaperContextMenu(e, paper)}
        title={hasPdf ? 'Double-click to open PDF · right-click for metadata' : 'Right-click for metadata'}
      >
        <div className="paper-title">{paper.title || 'Untitled'}</div>
        <div className="paper-year">{paper.year || 'No year'}</div>
        {!hasPdf && <span className="no-pdf-indicator">⚠️</span>}
      </div>
    );
  };

  const renderContextMenu = () => {
    if (!menu) return null;
    const paper = menu.paper || {};
    const branchTerms = Array.isArray(paper.branch_terms) ? paper.branch_terms : [];

    const baseStyle = {
      position: 'fixed',
      top: menu.y,
      left: menu.x,
      zIndex: 10000,
      background: 'white',
      border: '1px solid #999',
      borderRadius: 4,
      boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
      minWidth: 200,
      maxWidth: 360,
      fontSize: 13,
      color: '#222',
    };
    const itemStyle = {
      padding: '8px 12px',
      cursor: 'pointer',
      borderBottom: '1px solid #eee',
      userSelect: 'none',
    };
    const headerStyle = {
      padding: '6px 12px',
      fontWeight: 600,
      borderBottom: '1px solid #ddd',
      background: '#f5f5f5',
    };
    const bodyStyle = { padding: '8px 12px', whiteSpace: 'pre-wrap' };

    const stop = (e) => e.stopPropagation();

    if (menu.view === 'root') {
      return (
        <div style={baseStyle} onClick={stop} onMouseDown={stop} onContextMenu={(e) => e.preventDefault()}>
          <div
            style={itemStyle}
            onClick={() => setMenu({ ...menu, view: 'searchTerms' })}
          >
            Search Terms
          </div>
        </div>
      );
    }

    if (menu.view === 'searchTerms') {
      return (
        <div style={baseStyle} onClick={stop} onMouseDown={stop} onContextMenu={(e) => e.preventDefault()}>
          <div style={headerStyle}>Search Terms</div>
          <div style={bodyStyle}>
            {branchTerms.length > 0 ? branchTerms.join(', ') : 'None'}
          </div>
          <div
            style={{ ...itemStyle, borderBottom: 'none', textAlign: 'right', color: '#666' }}
            onClick={closeMenu}
          >
            Close
          </div>
        </div>
      );
    }

    return null;
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
      {renderContextMenu()}
    </div>
  );
}

export default PaperList;














