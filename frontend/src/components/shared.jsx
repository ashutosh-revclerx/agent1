export function Spinner() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-10 w-10 border-2 border-gray-200 border-t-gray-900" />
    </div>
  );
}

export function SummaryCard({ icon, label, value, small }) {
  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-4 hover:shadow-md transition-shadow">
      <div className="flex items-center gap-3">
        <span className="text-2xl">{icon}</span>
        <div>
          <p className="text-xs text-gray-500">{label}</p>
          <p className={`font-extrabold text-gray-900 ${small ? "text-base" : "text-2xl"} mt-0.5`}>{value}</p>
        </div>
      </div>
    </div>
  );
}
