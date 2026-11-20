import type { QCControls } from './outbreak-types';

export type WeeklyInput = { weeks: number; multiplier: string };
export type SimulationForm = QCControls & { weeklyInput?: WeeklyInput };

export function hospitalSettings(controls: QCControls) {
  const { hospitalizationRate, baselineOccupancy, lengthOfStayDays, admissionDelayDays,
    surgeActivationDay, surgeCapacity, holdingCapacity, bedAllotments, allocationPolicy,
    arrivalSplitPolicy, acknowledgeAssumedCapacity, compareAllocation } = controls;
  return { hospitalizationRate, baselineOccupancy, lengthOfStayDays, admissionDelayDays,
    surgeActivationDay, surgeCapacity, holdingCapacity, bedAllotments, allocationPolicy,
    arrivalSplitPolicy, acknowledgeAssumedCapacity, compareAllocation };
}
