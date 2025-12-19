import React from 'react';
import { BaseEdge, getBezierPath } from 'reactflow';

export default function WaypointEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  markerEnd,
  data
}) {
  const waypoints = data?.waypoints || [];
  
  // Build path through waypoints
  let path = '';
  
  if (waypoints && waypoints.length > 0) {
    // Start from source
    path = `M ${sourceX},${sourceY}`;
    
    // Add waypoints with smooth curves
    waypoints.forEach((wp) => {
      path += ` L ${wp.x},${wp.y}`;
    });
    
    // End at target
    path += ` L ${targetX},${targetY}`;
  } else {
    // Fallback to bezier if no waypoints
    const [edgePath] = getBezierPath({
      sourceX,
      sourceY,
      sourcePosition,
      targetX,
      targetY,
      targetPosition,
    });
    path = edgePath;
  }

  return (
    <BaseEdge
      id={id}
      path={path}
      style={style}
      markerEnd={markerEnd}
    />
  );
}
