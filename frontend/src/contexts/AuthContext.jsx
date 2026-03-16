import { createContext, useContext, useState, useEffect } from 'react';
import { api } from '../services/api';
import { auth } from '../firebase';
import { 
  onAuthStateChanged, 
  signInWithEmailAndPassword, 
  createUserWithEmailAndPassword, 
  signOut,
  getIdToken,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithRedirect,
  getRedirectResult
} from 'firebase/auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check for redirect result on mount
    const checkRedirect = async () => {
      try {
        const result = await getRedirectResult(auth);
        if (result) {
          console.log('Google redirect sign-in successful');
        }
      } catch (error) {
        console.error('Google redirect sign-in error:', error);
      }
    };
    checkRedirect();

    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      if (firebaseUser) {
        try {
          // Get ID token and store it for API calls
          const token = await getIdToken(firebaseUser);
          localStorage.setItem('token', token);
          
          // Fetch additional user data from our backend
          const userData = await api.getCurrentUser();
          setUser({ ...firebaseUser, ...userData });
        } catch (error) {
          console.error('Failed to sync user with backend:', error);
          // Even if backend fails, we have the firebase user
          setUser(firebaseUser);
        }
      } else {
        setUser(null);
        localStorage.removeItem('token');
        localStorage.removeItem('refreshToken');
      }
      setLoading(false);
    });

    return () => unsubscribe();
  }, []);

  const login = async (email, password) => {
    return signInWithEmailAndPassword(auth, email, password);
  };

  const register = async (username, email, password) => {
    // 1. Create user in Firebase
    const userCredential = await createUserWithEmailAndPassword(auth, email, password);
    
    // 2. Register in our backend to create the user document in MongoDB
    try {
      const token = await getIdToken(userCredential.user);
      localStorage.setItem('token', token);
      await api.register(username, email, password);
    } catch (error) {
      console.error('Backend registration failed:', error);
    }
    
    return userCredential;
  };

  const loginWithGoogle = async () => {
    const provider = new GoogleAuthProvider();
    try {
      return await signInWithPopup(auth, provider);
    } catch (error) {
      if (error.code === 'auth/popup-blocked') {
        return signInWithRedirect(auth, provider);
      }
      throw error;
    }
  };

  const loginWithGoogleRedirect = async () => {
    const provider = new GoogleAuthProvider();
    return signInWithRedirect(auth, provider);
  };

  const logout = async () => {
    return signOut(auth);
  };

  const value = {
    user,
    loading,
    login,
    loginWithGoogle,
    register,
    logout,
    isAuthenticated: !!user
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
