import numpy as np
import matplotlib.pyplot as plt
from scipy.fftpack import fft,ifft
import librosa
import soundfile as sf
import scipy.signal
import scipy.io.wavfile as wavfile
import wave
import argparse
d=0.008
c=344.0
position=[-7*d/2,-5*d/2,-3*d/2,-d/2,d/2,3*d/2,5*d/2,7*d/2]

# print(2*np.pi*21000/c)

def FFT(y,Fs):
#     y=filt_bp(y,Fs,f_low,f_high)
    L=len(y)

    Y=fft(y)
    p2=np.abs(Y/L)
    p1=p2[:int(L//2)]*2
    # p1=10*np.log10(p1)

    max_idx=np.argmax(p1)

    phi=np.angle(Y)[:int(L//2)]
    f=np.arange(int(L//2))*(Fs/L)

    max_f=f[max_idx]
    max_amp=p1[max_idx]
    max_phi=phi[max_idx]

    # print(max_f,max_amp,max_phi)
    return f,p1,phi, max_f, max_amp,max_phi

#########################以下是调制发送的音频的代码########################

def Generate_simplefreq_audio(freq,gene_path,fs=96000):
    t=np.arange(0,fs*4)/fs
    sig=0.5*np.cos(2*np.pi*freq*t)

    sf.write(gene_path, sig, fs)

def Read_1channel_audio(path):
    sig,sr=librosa.load(path,sr=None)

    return sig,sr

def modulate_das_angle(input_path, outputpath,target_theta=0, Iswrite=True):
    input_audio,sr=Read_1channel_audio(input_path)
    print(input_audio,sr)
    output_audio = np.zeros((8, len(input_audio)))

    frequencies=[18000,24000]
    idx1=int(frequencies[0]*len(input_audio)/sr)
    idx2=int(frequencies[1]*len(input_audio)/sr)

    # print(idx1,idx2)
    input_spec=np.fft.rfft(input_audio)
    f=np.arange(int(len(input_audio)//2))*(sr/len(input_audio))

    for i in range(8):
        output_spec=np.copy(input_spec)
        for j in range(idx1,idx2):
            select_f=f[j]
            wavelength=c/select_f
            phase_diff= - 2 * np.pi * i * d / wavelength * np.sin(np.radians(target_theta))
            output_spec[j]= input_spec[j] * np.exp(1.0j * phase_diff)

        output_audio[i]=np.fft.irfft(output_spec)

    if Iswrite:
        sf.write(outputpath, output_audio.T, sr)

    return output_audio,sr

def modulate_DaS_SDM(input_path1, theta1, input_path2, theta2, outputfolder):
    output_audio1,sr1=modulate_das_angle(input_path1,'',target_theta=theta1,Iswrite=False)
    output_audio2,sr2=modulate_das_angle(input_path2,'',target_theta=theta2,Iswrite=False)

    output_audio = (output_audio1 + output_audio2)/2

    name1=input_path1.split('/')[-1].split('.')[0]+'_'+str(theta1)
    name2=input_path2.split('/')[-1].split('.')[0]+'_'+str(theta2)

    outputpath=outputfolder+'DaS_'+name1+'_'+name2+'.wav'
    print(outputpath)

    if sr1==sr2:
        sf.write(outputpath, output_audio.T, sr1)
    else:
        print("采样率不相等")




def modulate_MVDR_angle(input_path, outputpath,target_theta=0,null_theta=30,Iswrite=True):
    input_audio,sr=Read_1channel_audio(input_path)
    print(input_audio,sr)
    output_audio = np.zeros((8, len(input_audio)))

    frequencies=[18000,24000]
    idx1=int(frequencies[0]*len(input_audio)/sr)
    idx2=int(frequencies[1]*len(input_audio)/sr)


    input_spec=np.fft.rfft(input_audio)
    f=np.arange(int(len(input_audio)//2))*(sr/len(input_audio))

    n=np.arange(0,8,1).reshape([-1,1])

    w=np.zeros((8,len(input_spec)),dtype=np.complex_)
    print(w.shape)
    for j in range(idx1,idx2):
        select_f=f[j]
        wavelength=c/select_f

        phase_diff= np.exp(- 1.0j * 2 * np.pi * n * d / wavelength * np.sin(np.radians(target_theta)))
        null_vec= np.exp( -1.0j * 2 * np.pi * n * d / wavelength * np.sin(np.radians(null_theta)))

        Rx=np.mat(1000*np.dot(null_vec,np.transpose(np.conj(null_vec)))+1*np.eye(8))
        a_theta_0 = np.mat(phase_diff)

        w1=Rx.I*a_theta_0/(a_theta_0.H *Rx.I*a_theta_0).H
        w1=np.squeeze(w1)
        w1=w1/np.max(w1)
        # print(w1)
        w[:,j]=w1

    for i in range(8):
        output_spec=np.copy(input_spec)
        for j in range(idx1,idx2):
            select_f=f[j]
            wavelength=c/select_f
            # phase_diff= - 2 * np.pi * i * d / wavelength * np.sin(np.radians(target_theta))
            # print(w[i:j],w[i:j].shape)
            output_spec[j]= input_spec[j] * w[i,j]

        output_audio[i]=np.fft.irfft(output_spec)


    print(output_audio.shape)
    if Iswrite:
        sf.write(outputpath, output_audio.T, sr)

    return output_audio,sr

def modulate_MVDR_SDM(input_path1, theta1, input_path2, theta2, outputfolder):
    # modulate_MVDR_angle(input_path, outputpath,target_theta=0,null_theta=30,Iswrite=True):
    output_audio1,sr1=modulate_MVDR_angle(input_path1,'',target_theta=theta1,null_theta=theta2,Iswrite=False)
    output_audio2,sr2=modulate_MVDR_angle(input_path2,'',target_theta=theta2,null_theta=theta1,Iswrite=False)

    output_audio = (output_audio1 + output_audio2)/2

    name1=input_path1.split('/')[-1].split('.')[0]+'_'+str(theta1)
    name2=input_path2.split('/')[-1].split('.')[0]+'_'+str(theta2)

    outputpath=outputfolder+'MVDR_'+name1+'_'+name2+'.wav'
    print(outputpath)

    if sr1==sr2:
        sf.write(outputpath, output_audio.T, sr1)
    else:
        print("采样率不相等")



##########以下是仿真收到的音频的代码####################

def Read_8channel_audio(output_path):
    sig,sr=librosa.load(output_path,sr=None, mono=False)

    return sig,sr

def Simu_Receive(input_audio,sr,theta):

    output_audio = np.zeros((8, len(input_audio[0])))
    frequencies=[18000,24000]
    idx1=int(frequencies[0]*len(input_audio[0])/sr)
    idx2=int(frequencies[1]*len(input_audio[0])/sr)

    for i in range(8):
        temp=input_audio[i]
        input_spec=np.fft.rfft(temp)
        f=np.arange(int(len(temp)//2))*(sr/len(temp))
        output_spec=input_spec

        for j in range(idx1,idx2):
            select_f=f[j]
            wavelength=c/select_f
            phase_diff= 2 * np.pi* i*d /wavelength * np.sin(np.radians(theta))

            output_spec[j]= input_spec[j] * np.exp(1j * phase_diff)

        output_audio[i]=np.fft.irfft(output_spec)

    output=np.sum(output_audio,axis=0)

    return output, sr

def Draw_beampattern(path):
    theta_list=np.arange(-90,91,1)
    # theta_list=np.arange(0,185,10)
    # print(theta_list)
    max_amp_list=[]

    input_audio,sr=Read_8channel_audio(path)
    for theta in theta_list:
        rec_audio,sr=Simu_Receive(input_audio,sr,theta)
        f,p1,phi, max_f, max_amp,max_phi=FFT(rec_audio,sr)
        print(theta,max_f,max_amp)

        max_amp_list.append(max_amp)

    plt.plot(theta_list,max_amp_list)


def LowPassAndWriteWav(input_path,output_path,output_rate=8000):
    cut_Freq= 16000.0  #low pass freq
    input_rate = 96000
    data,sr=librosa.load(input_path,sr=input_rate)

    cutoff_freq = cut_Freq / input_rate
    b, a = scipy.signal.butter(8, cutoff_freq, 'lowpass')

    filtered_data = scipy.signal.filtfilt(b, a, data)

    decimated_data = scipy.signal.decimate(filtered_data, int(input_rate / output_rate))

    output_file = output_path
    wavfile.write(output_file, output_rate, decimated_data.astype(data.dtype))


def Get_audio_Lowfreq(path,theta,outputfolder,lowfreq=True):
    input_audio,sr=Read_8channel_audio(path)
    output,sr=Simu_Receive(input_audio,sr,theta)

    if lowfreq:
        rec=output+0.1*output*output

        cut_Freq=8000
        cutoff_freq = cut_Freq / sr
        b, a = scipy.signal.butter(8, cutoff_freq, 'lowpass')

        filtered_data = scipy.signal.filtfilt(b, a, rec)

        filename=path.split('/')[-1]
        outputpath=outputfolder+'LowFreq_'+str(theta)+'_'+filename

        wavfile.write(outputpath, sr, filtered_data.astype(output.dtype))

    else:
        output=output/8
        filename=path.split('/')[-1]
        outputpath=outputfolder+'HighFreq_'+str(theta)+'_'+filename

        wavfile.write(outputpath, sr, output.astype(output.dtype))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description="Generates BF pattern.",
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--directions_phis", type=str, default="0,40")
    parser.add_argument("--channel8_wavpath", type=str, default="woman1ssbup_0_man1ssbup_40_8channel_optnullsteeringphaseshifted_d_0.008.wav")
    args = parser.parse_args()

    phis_str = args.directions_phis.split(",")
    target_angles = [int(phi) for phi in phis_str]

    for target_angle in target_angles:
        Get_audio_Lowfreq(args.channel8_wavpath, target_angle, "simu_lowfreq_audios/",lowfreq=True)
