import { Platform } from 'react-native';
import * as FileSystem from 'expo-file-system';
import * as SecureStore from 'expo-secure-store';

type TrackingEvent = {
  event: string;
  timestamp: string;
  metadata?: Record<string, any>;
};

type FileTrackingEvent = TrackingEvent & {
  filePath?: string;
  fileSize?: number;
  operation: 'create' | 'read' | 'update' | 'delete';
};

const API_URL = 'http://localhost:8000';

// Track general events
export const track = async (event: string, metadata?: Record<string, any>) => {
  const trackingEvent: TrackingEvent = {
    event,
    timestamp: new Date().toISOString(),
    metadata
  };

  try {
    // Store locally first
    await FileSystem.makeDirectoryAsync(
      `${FileSystem.documentDirectory}tracking`,
      { intermediates: true }
    );

    const filename = `${Date.now()}.json`;
    await FileSystem.writeAsStringAsync(
      `${FileSystem.documentDirectory}tracking/${filename}`,
      JSON.stringify(trackingEvent)
    );

    // Try to send to backend
    await sendToBackend(trackingEvent);
  } catch (error) {
    console.log('Tracking error (non-critical):', error);
  }
};

async function sendToBackend(event: TrackingEvent | FileTrackingEvent) {
  try {
    let token = '';
    
    // Only try to get token if SecureStore is available
    if (typeof SecureStore !== 'undefined') {
      try {
        token = (await SecureStore.getItemAsync('authToken')) || '';
      } catch (secureStoreError) {
        console.log('SecureStore not available:', secureStoreError);
      }
    }
    
    await fetch(`${API_URL}/track`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      },
      body: JSON.stringify(event)
    });
  } catch (error) {
    console.log('Failed to send tracking data:', error);
  }
}

// Track file operations
export const trackFileOperation = async (
  operation: FileTrackingEvent['operation'],
  filePath: string,
  metadata?: Record<string, any>
) => {
  try {
    const fileInfo = await FileSystem.getInfoAsync(filePath);
    
    await track('file_operation', {
      filePath,
      fileSize: fileInfo.exists ? fileInfo.size : undefined,
      operation,
      ...metadata
    });
  } catch (error) {
    console.log('File tracking error:', error);
  }
};

// Sync offline tracking data
export const syncTrackingData = async () => {
  try {
    const trackingDir = `${FileSystem.documentDirectory}tracking`;
    const dirInfo = await FileSystem.getInfoAsync(trackingDir);
    
    if (!dirInfo.exists) return;
    
    const files = await FileSystem.readDirectoryAsync(trackingDir);
    
    for (const file of files) {
      try {
        const content = await FileSystem.readAsStringAsync(`${trackingDir}/${file}`);
        const event = JSON.parse(content);
        
        await sendToBackend(event);
        await FileSystem.deleteAsync(`${trackingDir}/${file}`);
      } catch (error) {
        console.error(`Error syncing tracking file ${file}:`, error);
      }
    }
  } catch (error) {
    console.error('Error syncing tracking data:', error);
  }
};
