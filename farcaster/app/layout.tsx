import Script from 'next/script';

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <Script
          src="https://cdn.jsdelivr.net/npm/@multisynq/client@latest/bundled/multisynq-client.esm.js"
          strategy="afterInteractive"
          onLoad={() => console.log('Multisynq loaded')}
        />
        {children}
      </body>
    </html>
  );
}
