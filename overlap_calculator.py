"""
Overlap Calculator for Literature Review Visualizer
Builds hierarchy: Database → Query → Branch Term → Papers
(No overlap nodes - green nodes removed)
"""

from typing import List, Dict, Set, Optional
from collections import defaultdict
from ris_parser import RISParser, Paper
from config import find_newest_manual_grouping_file, find_newest_most_relevant_file


class OverlapCalculator:
    """Calculates paper organization and builds visualization hierarchy"""
    
    def __init__(self, queries: Dict):
        """
        Initialize with queries dict containing query names and their RIS files
        
        Args:
            queries: Dict mapping query names to query info (with 'ris_file' key)
        """
        self.queries = queries
        self.all_papers: List[Paper] = []
        self.papers_by_query_and_branch: Dict[str, Dict[str, List[Paper]]] = defaultdict(lambda: defaultdict(list))
        self.databases: Set[str] = set()
        # Store most-cited papers grouped by query and branch term
        self.most_cited_by_query_and_branch: Dict[str, Dict[str, List[Paper]]] = defaultdict(lambda: defaultdict(list))
        # Store most-relevant papers grouped by query and branch term
        self.most_relevant_by_query_and_branch: Dict[str, Dict[str, List[Paper]]] = defaultdict(lambda: defaultdict(list))
        
    def _get_canonical_term(self, term_variants: List[str]) -> str:
        """
        Return the term variant with the most capital letters.
        If tied, prefer the first occurrence.
        
        Args:
            term_variants: List of term variants (e.g., ["CT", "Ct", "ct"])
            
        Returns:
            The canonical term (the one with most capital letters)
        """
        if not term_variants:
            return None
        return max(term_variants, key=lambda t: sum(1 for c in t if c.isupper()))
        
    def load_papers_from_queries(self) -> Dict[str, str]:
        """
        Load papers from all RIS files specified in queries
        
        Returns:
            Dict mapping query names to database names
        """
        query_databases = {}
        
        # Store papers by query for reuse (avoid parsing twice)
        papers_by_query: Dict[str, List[Paper]] = {}
        
        # First pass: parse files and collect all branch term variants
        # Maps: normalized_term (lowercase) -> list of all variants seen
        term_variants_by_query: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
        
        for query_name, query_info in self.queries.items():
            ris_file = query_info.get('ris_file')
            if not ris_file:
                print(f"Warning: No RIS file specified for query '{query_name}'")
                continue
            
            # Parse RIS file
            parser = RISParser(ris_file)
            papers = parser.parse()
            database = parser.database
            
            self.databases.add(database)
            query_databases[query_name] = database
            papers_by_query[query_name] = papers
            
            # Collect all branch term variants (case-insensitively)
            for paper in papers:
                if paper.branch_terms:
                    for branch_term in paper.branch_terms:
                        normalized = branch_term.lower()
                        if branch_term not in term_variants_by_query[query_name][normalized]:
                            term_variants_by_query[query_name][normalized].append(branch_term)
        
        # Build canonical term mapping: normalized_term -> canonical_term
        canonical_term_map: Dict[str, Dict[str, str]] = {}
        for query_name, normalized_terms in term_variants_by_query.items():
            canonical_term_map[query_name] = {}
            for normalized, variants in normalized_terms.items():
                canonical = self._get_canonical_term(variants)
                canonical_term_map[query_name][normalized] = canonical
        
        # Second pass: organize papers using canonical terms
        for query_name, papers in papers_by_query.items():
            # Organize papers by branch term (using canonical terms)
            for paper in papers:
                self.all_papers.append(paper)
                
                # Add paper to each branch term it belongs to
                # Papers with no RN field or blank RN field have empty branch_terms list
                if paper.branch_terms and len(paper.branch_terms) > 0:
                    for branch_term in paper.branch_terms:
                        # Normalize to get the canonical term
                        normalized = branch_term.lower()
                        canonical_term = canonical_term_map[query_name].get(normalized, branch_term)
                        # Use canonical term for grouping
                        self.papers_by_query_and_branch[query_name][canonical_term].append(paper)
                else:
                    # If no branch terms (missing RN field or blank RN field), add to "uncategorized" group
                    self.papers_by_query_and_branch[query_name]["uncategorized"].append(paper)
        
        return query_databases
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison (lowercase, strip whitespace)"""
        if not text:
            return ""
        return text.lower().strip()
    
    def _match_paper(self, most_cited_paper: Paper) -> Optional[Paper]:
        """
        Match a paper from most_cited file to an existing paper by title OR DOI
        
        Args:
            most_cited_paper: Paper from most_cited file
            
        Returns:
            Matching existing Paper object, or None if no match
        """
        most_cited_title = self._normalize_text(most_cited_paper.title)
        most_cited_doi = self._normalize_text(most_cited_paper.doi)
        
        for existing_paper in self.all_papers:
            existing_title = self._normalize_text(existing_paper.title)
            existing_doi = self._normalize_text(existing_paper.doi)
            
            # Match by title OR DOI
            if most_cited_title and existing_title and most_cited_title == existing_title:
                return existing_paper
            if most_cited_doi and existing_doi and most_cited_doi == existing_doi:
                return existing_paper
        
        return None
    
    def load_most_cited_papers(self):
        """
        Load most-cited papers from manual_groupings folder.
        For each paper, find which branch term has the LEAST papers and assign it there.
        """
        most_cited_file = find_newest_manual_grouping_file()
        if not most_cited_file:
            print("No most_cited file found in manual_groupings folder")
            return
        
        # Parse most_cited file
        parser = RISParser(most_cited_file)
        most_cited_papers = parser.parse()
        
        print(f"Found {len(most_cited_papers)} papers in most_cited file")
        
        # Build mapping of branch term to paper count for each query
        # This helps us find which branch term has the least papers
        branch_term_counts: Dict[str, Dict[str, int]] = defaultdict(dict)
        for query_name in self.queries.keys():
            branch_terms = self.papers_by_query_and_branch.get(query_name, {})
            for branch_term, papers in branch_terms.items():
                branch_term_counts[query_name][branch_term] = len(papers)
        
        # Process each most-cited paper
        matched_count = 0
        for most_cited_paper in most_cited_papers:
            # Match to existing paper
            matched_paper = self._match_paper(most_cited_paper)
            if not matched_paper:
                continue
            
            matched_count += 1
            
            # Get branch terms from the most_cited file (they may differ from original)
            # Use the branch terms from most_cited file, but normalize them
            if not most_cited_paper.branch_terms:
                continue
            
            # Find which query this paper belongs to
            # We need to find which query contains this paper
            target_query = None
            for query_name, branch_terms_dict in self.papers_by_query_and_branch.items():
                for branch_term, papers in branch_terms_dict.items():
                    if matched_paper in papers:
                        target_query = query_name
                        break
                if target_query:
                    break
            
            if not target_query:
                continue
            
            # Find which branch term from most_cited file has the LEAST papers
            # We need to match branch terms case-insensitively to existing canonical terms
            min_count = float('inf')
            selected_branch_term = None
            
            for branch_term in most_cited_paper.branch_terms:
                normalized = branch_term.lower()
                # Find matching canonical term (case-insensitive match)
                matching_canonical = None
                for existing_branch_term in branch_term_counts[target_query].keys():
                    if existing_branch_term.lower() == normalized:
                        matching_canonical = existing_branch_term
                        break
                
                if matching_canonical:
                    count = branch_term_counts[target_query][matching_canonical]
                    if count < min_count:
                        min_count = count
                        selected_branch_term = matching_canonical
            
            if selected_branch_term:
                # Add paper to most-cited group for this branch term
                self.most_cited_by_query_and_branch[target_query][selected_branch_term].append(matched_paper)
        
        print(f"Matched {matched_count} most-cited papers to existing papers")
    
    def load_most_relevant_papers(self):
        """
        Load most-relevant papers from manual_groupings folder.
        For each paper, find which branch term has the LEAST papers and assign it there.
        Same logic as load_most_cited_papers but uses most_relevant file.
        """
        most_relevant_file = find_newest_most_relevant_file()
        if not most_relevant_file:
            print("No most_relevant file found in manual_groupings folder")
            return
        
        # Parse most_relevant file
        parser = RISParser(most_relevant_file)
        most_relevant_papers = parser.parse()
        
        print(f"Found {len(most_relevant_papers)} papers in most_relevant file")
        
        # Build mapping of branch term to paper count for each query
        # This helps us find which branch term has the least papers
        branch_term_counts: Dict[str, Dict[str, int]] = defaultdict(dict)
        for query_name in self.queries.keys():
            branch_terms = self.papers_by_query_and_branch.get(query_name, {})
            for branch_term, papers in branch_terms.items():
                branch_term_counts[query_name][branch_term] = len(papers)
        
        # Process each most-relevant paper
        matched_count = 0
        for most_relevant_paper in most_relevant_papers:
            # Match to existing paper
            matched_paper = self._match_paper(most_relevant_paper)
            if not matched_paper:
                continue
            
            matched_count += 1
            
            # Get branch terms from the most_relevant file (they may differ from original)
            # Use the branch terms from most_relevant file, but normalize them
            if not most_relevant_paper.branch_terms:
                continue
            
            # Find which query this paper belongs to
            # We need to find which query contains this paper
            target_query = None
            for query_name, branch_terms_dict in self.papers_by_query_and_branch.items():
                for branch_term, papers in branch_terms_dict.items():
                    if matched_paper in papers:
                        target_query = query_name
                        break
                if target_query:
                    break
            
            if not target_query:
                continue
            
            # Find which branch term from most_relevant file has the LEAST papers
            # We need to match branch terms case-insensitively to existing canonical terms
            min_count = float('inf')
            selected_branch_term = None
            
            for branch_term in most_relevant_paper.branch_terms:
                normalized = branch_term.lower()
                # Find matching canonical term (case-insensitive match)
                matching_canonical = None
                for existing_branch_term in branch_term_counts[target_query].keys():
                    if existing_branch_term.lower() == normalized:
                        matching_canonical = existing_branch_term
                        break
                
                if matching_canonical:
                    count = branch_term_counts[target_query][matching_canonical]
                    if count < min_count:
                        min_count = count
                        selected_branch_term = matching_canonical
            
            if selected_branch_term:
                # Add paper to most-relevant group for this branch term
                self.most_relevant_by_query_and_branch[target_query][selected_branch_term].append(matched_paper)
        
        print(f"Matched {matched_count} most-relevant papers to existing papers")
    
    def build_hierarchy(self) -> Dict:
        """
        Build hierarchical data structure: Database → Query → Branch Term → Papers
        
        Returns:
            Hierarchical dict structure
        """
        hierarchy = {}
        
        for query_name, query_info in self.queries.items():
            database = None
            for q_name, q_info in self.queries.items():
                if q_name == query_name:
                    ris_file = q_info.get('ris_file')
                    if ris_file:
                        parser = RISParser(ris_file)
                        database = parser.database
                        break
            
            if not database:
                continue
            
            if database not in hierarchy:
                hierarchy[database] = {}
            
            if query_name not in hierarchy[database]:
                hierarchy[database][query_name] = {}
            
            # Get all branch terms for this query
            branch_terms = self.papers_by_query_and_branch.get(query_name, {})
            
            for branch_term, papers in branch_terms.items():
                hierarchy[database][query_name][branch_term] = [p.to_dict() for p in papers]
        
        return hierarchy
    
    def get_visualization_data(self, hierarchy: Dict) -> Dict:
        """
        Generate React Flow visualization data (nodes and edges)
        Structure: Database → Query → Branch Term (no overlap nodes)
        
        Args:
            hierarchy: Hierarchical data from build_hierarchy()
            
        Returns:
            Dict with 'nodes' and 'edges' for React Flow
        """
        nodes = []
        edges = []
        
        # ID generators
        node_id_counter = {"database": 0, "query": 0, "branch": 0, "mostCited": 0, "uncategorized": 0, "mostCitedAggregate": 0, "mostRelevantAggregate": 0}
        
        def get_next_id(node_type: str) -> str:
            node_id_counter[node_type] += 1
            return f"{node_type}_{node_id_counter[node_type]}"
        
        # Layout constants
        database_y = 50
        query_y_offset = 150
        branch_y_offset = 150
        green_y_offset = 150  # Vertical offset for green nodes below blue nodes
        branch_x_spacing = 275  # Horizontal spacing between branch nodes
        database_x_spacing = 600  # Horizontal spacing between databases
        
        # Track positions
        current_database_x = 100
        
        # Process each database
        for database_name, queries in hierarchy.items():
            # Create database node
            database_node_id = get_next_id("database")
            database_x = current_database_x
            database_y_pos = database_y
            
            nodes.append({
                "id": database_node_id,
                "type": "database",
                "position": {"x": database_x, "y": database_y_pos},
                "data": {
                    "label": database_name.upper(),
                    "database": database_name
                }
            })
            
            # Process queries for this database
            query_y = database_y_pos + query_y_offset
            query_x_spacing = 400  # Horizontal spacing between queries
            query_start_x = database_x - (len(queries) - 1) * query_x_spacing / 2
            
            # Track green nodes and query positions for red node creation
            all_green_node_ids = []  # Track all green node IDs for this database
            all_most_cited_papers_for_db = []  # Collect all most-cited papers
            all_most_relevant_papers_for_db = []  # Collect all most-relevant papers
            query_node_x = None  # Track query node x position for red node alignment
            max_green_y = 0  # Track maximum green node y position
            
            query_idx = 0
            for query_name, branch_terms in queries.items():
                # Create query node
                query_node_id = get_next_id("query")
                query_x = query_start_x + (query_idx * query_x_spacing)
                
                # Track query x position for red node alignment (use first query or center query)
                if query_idx == 0 or len(queries) == 1:
                    query_node_x = query_x
                
                query_info = self.queries.get(query_name, {})
                query_string = query_info.get('query', query_name)
                
                nodes.append({
                    "id": query_node_id,
                    "type": "query",
                    "position": {"x": query_x, "y": query_y},
                    "data": {
                        "label": query_name,
                        "query": query_string,
                        "query_name": query_name
                    }
                })
                
                # Edge from database to query
                edges.append({
                    "id": f"{database_node_id}-{query_node_id}",
                    "source": database_node_id,
                    "target": query_node_id,
                    "type": "smoothstep"
                })
                
                # Process branch terms for this query
                # Filter out "uncategorized" - it will be handled separately at database level
                branch_terms_filtered = {k: v for k, v in branch_terms.items() if k != "uncategorized"}
                branch_terms_list = sorted(branch_terms_filtered.items(), key=lambda x: x[0].lower())
                if branch_terms_list:
                    # Calculate starting x position to center branches under query
                    num_branches = len(branch_terms_list)
                    total_width = (num_branches - 1) * branch_x_spacing
                    start_x = query_x - total_width / 2
                    
                    # All branches at the same y level (same row)
                    branch_y = query_y + branch_y_offset
                    
                    # Track blue node IDs for green node creation
                    blue_node_map: Dict[str, str] = {}  # Maps (query_name, branch_term) -> branch_node_id
                    
                    for branch_idx, (branch_term, branch_papers) in enumerate(branch_terms_list):
                        branch_node_id = get_next_id("branch")
                        branch_x = start_x + (branch_idx * branch_x_spacing)
                        
                        # Store mapping for green node creation
                        blue_node_map[(query_name, branch_term)] = branch_node_id
                        
                        # Get all papers for this branch term
                        all_branch_papers = self.papers_by_query_and_branch.get(query_name, {}).get(branch_term, [])
                        paper_count = len(all_branch_papers)
                        
                        # Clean branch_term: remove "AND " prefix if it exists
                        clean_branch_term = branch_term.strip()
                        if clean_branch_term.upper().startswith("AND "):
                            clean_branch_term = clean_branch_term[4:].strip()
                        
                        nodes.append({
                            "id": branch_node_id,
                            "type": "branchTerm",
                            "position": {"x": branch_x, "y": branch_y},
                            "data": {
                                "label": f"AND {clean_branch_term}",
                                "branch_term": branch_term,
                                "query_name": query_name,
                                "papers": [p.to_dict() for p in all_branch_papers],
                                "paper_count": paper_count
                            }
                        })
                        
                        # Edge from query to branch term
                        edges.append({
                            "id": f"{query_node_id}-{branch_node_id}",
                            "source": query_node_id,
                            "target": branch_node_id,
                            "type": "smoothstep"
                        })
                    
                    # Create green nodes for most-cited papers
                    most_cited_papers = self.most_cited_by_query_and_branch.get(query_name, {})
                    for branch_term, cited_papers in most_cited_papers.items():
                        if not cited_papers:
                            continue
                        
                        # Find the blue node ID for this branch term
                        blue_node_id = blue_node_map.get((query_name, branch_term))
                        if not blue_node_id:
                            continue
                        
                        # Find the blue node to get its position
                        blue_node = next((n for n in nodes if n["id"] == blue_node_id), None)
                        if not blue_node:
                            continue
                        
                        # Create green node below blue node
                        green_node_id = get_next_id("mostCited")
                        green_x = blue_node["position"]["x"]
                        green_y = blue_node["position"]["y"] + green_y_offset
                        
                        # Track green node for orange node connections
                        all_green_node_ids.append(green_node_id)
                        all_most_cited_papers_for_db.extend(cited_papers)
                        max_green_y = max(max_green_y, green_y)
                        
                        nodes.append({
                            "id": green_node_id,
                            "type": "overlapGroup",
                            "position": {"x": green_x, "y": green_y},
                            "data": {
                                "label": "Most cited (or of interest)",
                                "papers": [p.to_dict() for p in cited_papers],
                                "paper_count": len(cited_papers)
                            }
                        })
                        
                        # Edge from blue node to green node
                        edges.append({
                            "id": f"{blue_node_id}-{green_node_id}",
                            "source": blue_node_id,
                            "target": green_node_id,
                            "type": "smoothstep"
                        })
                    
                query_idx += 1
            
            # Collect most-relevant papers from all queries for this database (for red node)
            for query_name in queries.keys():
                most_relevant_papers = self.most_relevant_by_query_and_branch.get(query_name, {})
                for branch_term, relevant_papers in most_relevant_papers.items():
                    if relevant_papers:
                        all_most_relevant_papers_for_db.extend(relevant_papers)
            
            # Create "Found outside search" node for uncategorized papers at database level
            # Collect all uncategorized papers from all queries in this database
            all_uncategorized_papers = []
            for query_name in queries.keys():
                uncategorized_papers = self.papers_by_query_and_branch.get(query_name, {}).get("uncategorized", [])
                all_uncategorized_papers.extend(uncategorized_papers)
            
            uncategorized_node_id = None
            if all_uncategorized_papers:
                # Create purple node at database level, positioned to the far left
                uncategorized_node_id = get_next_id("uncategorized")
                # Position to the far left, outside of all branch nodes, aligned vertically with database
                # Calculate leftmost position: database_x minus enough space to be clearly outside
                # Branch nodes can extend left, so position well to the left
                uncategorized_x = current_database_x - 500  # Far left, well outside of branch nodes
                uncategorized_y = database_y_pos  # Same y as database node
                
                nodes.append({
                    "id": uncategorized_node_id,
                    "type": "database",  # Use database node type but with purple styling
                    "position": {"x": uncategorized_x, "y": uncategorized_y},
                    "data": {
                        "label": "Found outside search",
                        "database": "uncategorized",
                        "papers": [p.to_dict() for p in all_uncategorized_papers],
                        "paper_count": len(all_uncategorized_papers),
                        "is_uncategorized": True  # Flag to identify this special node
                    }
                })
            
            # Create orange "Most cited (or of interest)" aggregation node
            # Collect all papers from green nodes and purple node
            orange_node_id = None
            if all_green_node_ids or all_uncategorized_papers:
                # Add purple node papers to aggregation
                if all_uncategorized_papers:
                    all_most_cited_papers_for_db.extend(all_uncategorized_papers)
                
                # Remove duplicates (papers might appear in multiple green nodes)
                # Use paper ID to deduplicate
                seen_paper_ids = set()
                unique_most_cited_papers = []
                for paper in all_most_cited_papers_for_db:
                    # Papers are Paper objects, get ID
                    paper_id = paper.id if hasattr(paper, 'id') else None
                    if paper_id and paper_id not in seen_paper_ids:
                        seen_paper_ids.add(paper_id)
                        unique_most_cited_papers.append(paper)
                    elif not paper_id:
                        # If no ID, add anyway (shouldn't happen but be safe)
                        unique_most_cited_papers.append(paper)
                
                if unique_most_cited_papers:
                    # Create orange node
                    orange_node_id = get_next_id("mostCitedAggregate")
                    # Position: horizontally aligned with query node, below all green nodes
                    orange_node_x = query_node_x if query_node_x is not None else database_x
                    orange_node_y = max_green_y + 150 if max_green_y > 0 else query_y + branch_y_offset + green_y_offset + 150
                    
                    # Convert papers to dict format
                    orange_node_papers = [p.to_dict() for p in unique_most_cited_papers]
                    
                    nodes.append({
                        "id": orange_node_id,
                        "type": "overlapGroup",  # Reuse overlapGroup type with orange styling
                        "position": {"x": orange_node_x, "y": orange_node_y},
                        "data": {
                            "label": "Most cited (or of interest)",
                            "papers": orange_node_papers,
                            "paper_count": len(orange_node_papers),
                            "is_most_cited_aggregate": True  # Flag for orange styling
                        }
                    })
                    
                    # Create edges from all green nodes to orange node
                    for green_node_id in all_green_node_ids:
                        edges.append({
                            "id": f"{green_node_id}-{orange_node_id}",
                            "source": green_node_id,
                            "target": orange_node_id,
                            "type": "smoothstep"
                        })
                    
                    # Create edge from purple node to orange node
                    if uncategorized_node_id:
                        edges.append({
                            "id": f"{uncategorized_node_id}-{orange_node_id}",
                            "source": uncategorized_node_id,
                            "target": orange_node_id,
                            "type": "smoothstep"
                        })
            
            # Create red "Most relevant" aggregation node
            # Collect all papers from most_relevant_by_query_and_branch ONLY (no uncategorized papers)
            if all_most_relevant_papers_for_db:
                # Remove duplicates (papers might appear in multiple sources)
                # Use paper ID to deduplicate
                seen_paper_ids = set()
                unique_most_relevant_papers = []
                for paper in all_most_relevant_papers_for_db:
                    # Papers are Paper objects, get ID
                    paper_id = paper.id if hasattr(paper, 'id') else None
                    if paper_id and paper_id not in seen_paper_ids:
                        seen_paper_ids.add(paper_id)
                        unique_most_relevant_papers.append(paper)
                    elif not paper_id:
                        # If no ID, add anyway (shouldn't happen but be safe)
                        unique_most_relevant_papers.append(paper)
                
                if unique_most_relevant_papers:
                    # Create red node
                    red_node_id = get_next_id("mostRelevantAggregate")
                    # Position: to the immediate right of orange node, same y level
                    red_node_x = (orange_node_x + 300) if orange_node_id else (query_node_x + 300 if query_node_x is not None else database_x + 300)
                    red_node_y = orange_node_y if orange_node_id else (max_green_y + 150 if max_green_y > 0 else query_y + branch_y_offset + green_y_offset + 150)
                    
                    # Convert papers to dict format
                    red_node_papers = [p.to_dict() for p in unique_most_relevant_papers]
                    
                    nodes.append({
                        "id": red_node_id,
                        "type": "overlapGroup",  # Reuse overlapGroup type with red styling
                        "position": {"x": red_node_x, "y": red_node_y},
                        "data": {
                            "label": "Most relevant",
                            "papers": red_node_papers,
                            "paper_count": len(red_node_papers),
                            "is_most_relevant_aggregate": True  # Flag for red styling
                        }
                    })
                    
                    # Create edge from orange node to red node ONLY (no connection to purple node or green nodes)
                    if orange_node_id:
                        edges.append({
                            "id": f"{orange_node_id}-{red_node_id}",
                            "source": orange_node_id,
                            "target": red_node_id,
                            "type": "smoothstep"
                        })
            
            # Move to next database position
            current_database_x += database_x_spacing
        
        return {
            "nodes": nodes,
            "edges": edges
        }




