export type ArrivalPolicy = 'nearest' | 'nearest_three_equal' | 'markov_proximity' | 'markov_preference';
export type AllocationPolicy = 'first_hospital' | 'next_probability' | 'nearest' | 'optimized';
export interface MovieHospital {
  id: string; name: string; coordinates: [number, number]; coordinateStatus: string;
  coordinateSourceUrl: string; sourceAsOf: string; dengueInpatientEligible: null;
  accreditedBeds: number; normalStaffedCapacity: null; dengueUsableBeds: null;
  primarySourceUrl: string;
}
export interface MovieBarangay {
  mappedFavoriteHospitalId?: string | null;
  id: string; name: string; coordinates: [number, number]; weight: number;
  observedAnnualCases: number | null;
  predictedAnnualCases?: number | null; burdenRank?: number | null; isHighBurdenCandidate?: boolean;
  nearestHospitals: { facilityId: string; distanceKm: number }[];
  hospitalsWithinBarangay?: { facilityId: string; distanceKm: number }[];
}
export interface MovieContext {
  weeklyOriginShares?: Record<string, Record<string, number>>[];
  firstAdmissionOriginShares?: Record<string, Record<string, number>>;
  hotspotRanking?: { model: string; criterion: string; artifactSha256: string; candidateIds: string[] } | null;
  referenceForecastRunId: string; weightYear: number; distanceMethod: string;
  barangays: MovieBarangay[]; hospitals: MovieHospital[];
}
export interface MovieParameters {
  forecastRunId: string; scenarioKind: 'hypothetical_shock' | 'historical_replay'; acknowledgeHypotheticalHospitalNetwork: true;
  autoHotspots?: boolean; allocationPolicy?: AllocationPolicy;
  arrivalSplitPolicy?: ArrivalPolicy;
  acknowledgeHypotheticalDates: true; startDate: string; endDate: string; seedBarangayId: string;
  extraCasesPerWeek: number; initialRadiusKm: number; expansionKmPerDay: number; growthDays: number;
  shockProfile: 'step' | 'ramp'; hospitalizationRate: number; lengthOfStayDays: number;
  baselineOccupancy: number; admissionDelayDays: number; surgeActivationDay: number;
  facilities: { facilityId: string; assumedDengueEligible: true; normalCapacity: number; surgeCapacity: number; holdingCapacity: number }[];
}
export interface MovieDay {
  weeklyCasesChangePct?: number | null;
  arrivalWeekIndex?: number;
  dayIndex: number; date: string; snapshotAt: string; intervalStart: string; intervalEnd: string;
  expectedCases: number; baselineCases: number; shockCases: number; cumulativeCases: number;
  cumulativeBaselineCases: number; cumulativeShockCases: number; assumedRadiusKm: number;
  arrivals: number; discharges: number; supportedCensus: number; holdingCensus: number;
  cumulativeArrivals: number; cumulativeDischarges: number; cumulativeUnresolved: number; balanceError: number;
  hotspotIds: string[];
  expansionRing: [number, number][];
  caseRange?: CaseRange; dailyCaseRange?: Pick<CaseRange, 'lowerCases' | 'upperCases'>;
  bedForecast?: BedForecast;
  barangays: { barangayId: string; expectedBedsShort?: number; expectedCases: number; baselineCases: number; shockCases: number; cumulativeCases: number; caseRange?: Pick<CaseRange, 'lowerCases' | 'upperCases'> }[];
  placementsByOrigin?: Record<string, { supported: number[]; holding: number[] }>;
  firstHospitalRoutes?: { firstFacilityId: string; facilityId: string; supportedPlacements: number; holdingPlacements: number }[];
  assignments: { barangayId: string; facilityId: string; supportedPlacements: number; holdingPlacements: number; distanceKm: number }[];
  facilities: { facilityId: string; normalCapacity: number; activatedSurgeCapacity: number; supportedCensus: number;
    firstAdmissionsToday?: number; supportedPlacementsToday?: number; holdingPlacementsToday?: number; unplacedToday?: number;
    nearestHotspot?: { barangayId: string; distanceKm: number } | null;
    bedForecast?: BedForecast;
    supportedCapacity: number; remainingSupportedCapacity: number; assumedNonDengueCensus: number;
    normalDengueCensus: number; surgeDengueCensus: number; holdingCensus: number; normalOccupancyPct: number; supportedOccupancyPct: number }[];
}
export interface BedForecast {
  weeklyDemandChangePct?: number | null;
  hospitalBedsRequired?: number; hospitalBedsShort?: number; hospitalsShort?: number;
  demandUtilizationPct?: number | null; utilizationDefinition?: string;
  baselineExpectedBeds?: number; baselineStaffedBedsRequired?: number; additionalStaffedBedsDueToSurge?: number;
  expectedBeds: number; lowerBeds: number | null; upperBeds: number | null;
  staffedBedsRequired: number; lowerStaffedBedsRequired: number | null; upperStaffedBedsRequired: number | null;
  assumedSupportedDengueCapacity: number; additionalStaffedBedsNeeded: number; additionalBedsUpperScenario: number | null;
  rangeKind: string;
}
export interface HospitalChoice {
  facilityId: string; share: number; expectedAdmissions: number;
  breakdown?: { distanceKm: number; proximityShare: number; preferenceMultiplier: number };
  peakStaffedBedsRequired: number; baselinePeakStaffedBedsRequired: number; additionalStaffedBedsDueToSurge: number;
}
export interface BedProjection extends BedForecast {
  peakDemandUtilizationPct?: number | null;
  baselinePeakStaffedBedsRequired?: number; peakAdditionalStaffedBedsDueToSurge?: number;
  arrivalSplitPolicy?: ArrivalPolicy;
  placePeaks?: { barangayId: string; hospitals: HospitalChoice[] }[];
  peakDate: string; peakDayIndex: number; peakLowerStaffedBedsRequired: number | null; peakUpperStaffedBedsRequired: number | null;
  peakAdditionalStaffedBedsNeeded: number; initialCensusAssumption: string;
  hospitalPeaks: { facilityId: string; peakStaffedBedsRequired: number; baselinePeakStaffedBedsRequired?: number; additionalStaffedBedsDueToSurge?: number; peakDemandUtilizationPct?: number | null }[];
}
export interface CaseRange { lowerCases: number; upperCases: number; coverageTarget: number; calibrationSamples: number; method: string }
export interface QCControls {
  reconstructHistory?: boolean;
  weeklyForecastId?: string | null;
  startDate: string; endDate: string; mode: 'forecast' | 'hypothetical_shock'; extraCasesPerWeek: number;
  growthDays: number; surgeCapacity: number; holdingCapacity: number;
  hospitalizationRate: number; baselineOccupancy: number; lengthOfStayDays: number;
  admissionDelayDays: number; surgeActivationDay: number; acknowledgeAssumedCapacity: true;
  allocationPolicy: 'first_hospital' | 'next_probability'; compareAllocation: boolean;
  arrivalSplitPolicy?: ArrivalPolicy;
  horizonDays?: number; weatherProfile?: 'typical' | 'wetter' | 'drier' | 'hotter';
  surgeEnabled?: boolean; surgeOnsetDay?: number; surgeMultiplier?: number;
  /** Optional user-imported per-hospital allotments (assumptions); hospitals not listed use the uniform values. */
  bedAllotments?: BedAllotment[] | null;
}
export type BedAllotment = ({ staffedBeds: number } | { dengueBeds: number; nonDengueBeds: number }) & {
  facilityId: string; holdingSpaces?: number | null;
  /** Extra staffed beds on top of the hospital's beds; null/absent keeps the scenario default (all for dengue). */
  extraDengueBeds?: number | null; extraNonDengueBeds?: number | null;
  /** Part of holdingSpaces kept for non-dengue patients; null/absent applies the initial 2:3 split. */
  nonDengueHoldingSpaces?: number | null;
}
export interface BedAllotmentImport {
  allotments: (BedAllotment & { name: string })[]; errors: { row: number; message: string }[];
  hospitalsNotInFile: string[]; hospitalCount: number; measurementKind: 'assumption'; caveat: string;
}
export interface QCWorkspaceResult extends OutbreakMovie {
  workspaceTab?: 'future' | 'historical';
  controlValues: QCControls; inputLimits: Record<string, { min: number; max: number; units: string }>;
  historicalWindows?: { startDate: string; endDate: string; kind?: 'training_archive' | 'forecast'; forecastAvailableFrom?: string }[];
  forecastEvidence: { id: string; issueBlock: { YR: number; WN: number } | null; model: string;
    weeklyCases?: { year: number; week: number; cityCases: number; barangayCases: Record<string, number>;
      scenarioCityCases?: number; scenarioBarangayCases?: Record<string, number> }[];
    caseSourceKind?: 'gp_reconstruction' | 'forecast'; observedReferenceBlock?: { YR: number; WN: number };
    unassignedWindowCases?: number; observationSource?: string;
    environmentalInputs: { sourceColumn: string; valueAtOrigin: number; unit: string; lagsSourceBlocks: number[] }[];
    observedCasesAtOrigin: number | null; observedSourceYearToDateCases: number | null; intervalCoverageTarget: number | null; trainedThrough: number | null; targetWeeks: { year: number; week: number }[];
    intervalCaveat: string; spatialCaveat: string; availabilityAssumption: string };
  periodSummary: { expectedCases: number; caseRange: CaseRange | null; barangays: MovieDay['barangays'] };
  forecastBacktest: { horizon: number; n: number; weatherMae: number; casesOnlyMae: number; persistenceMae: number; empiricalRangeCoverage: number }[];
  referenceSelectionAssumption: string; rangeInterpretation: string; simulationResultSha256: string;
  futureForecast?: { asOfDate: string; trainingCutoffBlock: { YR: number; WN: number }; selectedModel: string;
    modelSha256: string; sourcePeriodStart: string; sourcePeriodEnd: string;
    parameterAudit: { startDate: string; endDateExclusive: string; horizonDays: number;
      surgeOnsetDate: string | null; fullMultiplierDate: string | null; fullMultiplierReached: boolean;
      maximumAppliedMultiplier: number; staffedSurgeActivationSnapshotDate: string; staffedSurgeActivationWithinWindow: boolean;
      admissionDelayDays: number; lengthOfStayDays: number };
  };
  firstAdmissionComparison?: { arrivalSplitPolicy: ArrivalPolicy; peakBedsShort: number; peakShortageDate: string | null; cumulativeUnresolved: number; peakExpectedBeds: number }[];
}
export interface OutbreakMovie {
  progressionMethod?: 'gp_weekly_barangay_reconstruction' | 'production_weekly_barangay_forecast' | 'dated_QC_forecast_allocated_by_xgboost_annual_burden_shares' | 'dated_QC_forecast_allocated_by_prior_annual_barangay_shares' | 'explicit_hypothetical_radial_shock';
  schemaVersion: string; scenarioId: string; resultSha256: string; runTimestamp: string;
  parameters: MovieParameters; context: MovieContext; days: MovieDay[]; durationDays: number;
  mapScaleMaxDailyCases: number; assumptions: string; disclaimer: string;
  bedProjection?: BedProjection;
}
