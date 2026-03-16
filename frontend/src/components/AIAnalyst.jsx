import React from 'react';

const LIBRECHAT_URL = "http://localhost:3080";

const AIAnalyst = () => {
  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 80px)' }}>
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-2xl font-bold text-blue-900 flex items-center gap-3">
            <span>🧠</span> AI Analyst
          </h2>
          <p className="text-blue-600/80 text-sm">
            Powered by LibreChat
          </p>
        </div>
        <a
          href={LIBRECHAT_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded-lg transition-colors flex items-center gap-2"
        >
          <span>🚀</span> Open Full Screen
        </a>
      </div>

      <div className="flex-1 bg-white rounded-2xl shadow-xl overflow-hidden border border-blue-100">
        <iframe
          src={LIBRECHAT_URL}
          title="LibreChat AI Analyst"
          className="w-full h-full border-none"
          allow="accelerometer; ambient-light-sensor; camera; encrypted-media; geolocation; gyroscope; hid; microphone; midi; payment; usb; vr; xr-spatial-tracking"
          sandbox="allow-forms allow-modals allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts allow-downloads"
        />
      </div>
    </div>
  );
};

export default AIAnalyst;
