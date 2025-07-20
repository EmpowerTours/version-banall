import React from 'react';

export default function SafeAreaContainer({ children, insets }) {
  return (
    <div style={{ paddingTop: insets?.top || 0, paddingBottom: insets?.bottom || 0 }}>
      {children}
    </div>
  );
}
