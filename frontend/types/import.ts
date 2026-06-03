export interface ImportJobResponse {
  job_id: string;
  title: string;
  file_type: string;
  status: "pending" | "processing" | "completed" | "failed" | "cancelled";
  total_chunks: number;
  processed_chunks: number;
  memories_created: number;
  started_at: string | null;
  completed_at: string | null;
  progress_pct: number;
  error: string | null;
}

export interface ImportJobListResponse {
  jobs: ImportJobResponse[];
  total: number;
}
