import { api } from './client'
export const listZones = (cameraId) => api.get(`/cameras/${cameraId}/zones`)
export const createZone = (cameraId, data) => api.post(`/cameras/${cameraId}/zones`, data)
export const deleteZone = (cameraId, zoneId) => api.delete(`/cameras/${cameraId}/zones/${zoneId}`)
