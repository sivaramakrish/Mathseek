import * as SecureStore from 'expo-secure-store';
import * as crypto from 'expo-crypto';

const ANON_ID_KEY = 'mathseek_anon_id';

export const getAnonId = async (): Promise<string> => {
  let anonId = await SecureStore.getItemAsync(ANON_ID_KEY);
  if (!anonId) {
    anonId = crypto.randomUUID();
    await SecureStore.setItemAsync(ANON_ID_KEY, anonId);
  }
  return anonId;
};

export const track = async (action: string, metadata: object = {}) => {
  try {
    const anonId = await getAnonId();
    const authToken = await SecureStore.getItemAsync('auth_token');
    await fetch('http://localhost:8000/track', {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({
        action,
        anon_id: anonId,
        ...metadata
      }),
      credentials: 'include'
    });
  } catch (error) {
    console.error('Tracking error:', error);
  }
};