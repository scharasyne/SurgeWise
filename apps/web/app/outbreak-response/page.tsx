import QCSimulationWorkspace from '@/components/qc-simulation-workspace';
import './qc-simulation.css';

export default async function OutbreakResponse({ searchParams }: { searchParams: Promise<{ weeklyForecastId?: string; mode?: string }> }) {
  const { weeklyForecastId, mode } = await searchParams;
  return <QCSimulationWorkspace key={weeklyForecastId ?? mode ?? 'historical'} weeklyForecastId={weeklyForecastId}
    initialTab={weeklyForecastId || mode === 'future' ? 'future' : 'historical'} openSettings={mode === 'future'} />;
}
