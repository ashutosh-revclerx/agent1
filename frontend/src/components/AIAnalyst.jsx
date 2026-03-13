import React from 'react';

const AIAnalyst = () => {
  const LIBRECHAT_URL = "http://localhost:3080";

  return (
    <div className="flex flex-col h-[calc(100vh-140px)]">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-bold text-blue-900 flex items-center gap-3">
            <span>🧠</span> AI Analyst
          </h2>
          <p className="text-blue-600/80">
            Powered by LibreChat. Ask questions about your monitoring sessions and LLM traces.
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

      <div className="flex-1 bg-white rounded-2xl shadow-xl overflow-hidden border border-blue-100 relative">
        <iframe
          src={LIBRECHAT_URL}
          title="LibreChat AI Analyst"
          className="w-full h-full border-none"
          allow="accelerometer; ambient-light-sensor; camera; encrypted-media; geolocation; gyroscope; hid; microphone; midi; payment; usb; vr; xr-spatial-tracking"
          sandbox="allow-forms allow-modals allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts allow-downloads"
        />
      </div>
      
      <div className="mt-4 p-4 bg-blue-100/50 border border-blue-200 rounded-xl flex items-start gap-3">
        <span className="text-xl">💡</span>
        <div className="text-sm text-blue-800">
          <p className="font-bold mb-1">How to use our system data in Chat:</p>
          <ul className="list-disc list-inside space-y-1 opacity-90">
            <li>In LibreChat, create an <b>Agent</b> or use the <b>Actions</b> tool.</li>
            <li>Ask questions like: <i>"Show me the latest anomalies"</i> or <i>"Explain the root cause of the last incident."</i></li>
            <li>The chat will automatically fetch context from our backend.</li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default AIAnalyst;
