import pydicom
import os
import numpy as np
from skimage.morphology import disk, binary_dilation 
from cyvlfeat.fisher import fisher
from sklearn.linear_model import LogisticRegression
from numba import cuda
import pickle


class Classifier:
    def __init__(self, fileData, rawDataPath, maskDataPath):
        self.PATH = '/home/faqih/ITB/TA/Web/server/static/classificationModel'
        self.patSize = 7
        self.fileName = fileData['fileName']
        self.filePath = (rawDataPath + '/' + fileData['fileName'])
        self.patientID = fileData['patientID']
        self.nRegion = 8
        self.dictSize = 64
        self.compIndex = 8
        self.tumorMaskPath = np.load(os.path.join(maskDataPath, self.fileName.split('.',1)[0]+'.npz'))['mask']
        self.index = (np.load(os.path.join(self.PATH ,'cvIndex.npz')))['cvind']
        self.label = (np.load(os.path.join(self.PATH, 'label.npz')))['label']
        self.trainInd = np.uint16(np.where(self.index!=(1))[1])
        self.trainLabel = self.label[self.trainInd]
        self.trainFeaMat = ((np.load(os.path.join(self.PATH, 'feaMat.npz')))['feaMat'])[:, self.trainInd]
        self.cluFeasAvg = np.mean(((np.load(os.path.join(self.PATH, 'cluFeas.npz')))['cluFeas']), 1)
        self.means = (np.load(os.path.join(self.PATH, 'means.npz')))['means']
        self.priors = (np.load(os.path.join(self.PATH, 'priors.npz')))['priors']
        self.covariances = (np.load(os.path.join(self.PATH, 'covariances.npz')))['covariances']
        self.principalComp = (np.load(os.path.join(self.PATH, 'principalComp.npz')))['principalComp']
        self.tumorSize = 0

    def _norm(self, image):
        minElm = np.amin(image)
        maxElm = np.amax(image)
        normImage = np.true_divide((np.subtract(image, minElm)), (maxElm - minElm))
        return normImage 
        
    def _regionInd(self, normImage, dilMask, nRegion):
        intensities = normImage[dilMask]
        quantiles = np.float32(np.quantile(intensities, np.linspace(0, 1, nRegion+1)))
        regInd = np.zeros(intensities.size)
        for i in range (nRegion):
            ind = np.logical_and((intensities>=quantiles[i]), (intensities<=quantiles[i+1]))
            regInd[ind] = i
        return regInd
    
    def _extractLocFeas(self, normImage, dilMask, patSize):
        (r, c) = np.float32(dilMask.nonzero())
        offset = (patSize-1)/2
        x = np.linspace(-offset, offset, patSize, dtype='float32')
        [x, y] = np.meshgrid (x, x)
        rDelta = x 
        cDelta = y
        feas = np.zeros((patSize**2, c.size), dtype='float32')
        n = 0 
        for i in range(patSize):
            for j in range(patSize):
                rShifted = r + rDelta[i, j]
                cShifted = c + cDelta[i, j]      
                feas[n, :] = normImage[rShifted.astype(int), cShifted.astype(int)]
                n += 1 
        self.tumorSize = np.around((r.shape[0] * 0.49 * 0.49), decimals=2) 
        return feas

    def _featuresExtraction(self):
        testFeaMat = np.empty(((self.compIndex) * 2 * self.dictSize * self.nRegion, 0), dtype='float32')
        temp = []
        normImage = np.empty([2,2])
        image = pydicom.filereader.dcmread(self.filePath).pixel_array
        mask = self.tumorMaskPath   
        normImage = self._norm(image)
        se = disk(2)
        dilMask = binary_dilation(mask, se)
        feas = self._extractLocFeas(normImage, dilMask, self.patSize)
        feas = np.matmul(self.principalComp,(feas - self.cluFeasAvg[:,None]))
        regInd = self._regionInd(normImage, dilMask, self.nRegion)
        for j in range(self.nRegion):
            temp = np.append(temp, fisher(feas[::, regInd==j], self.means.transpose(), 
                     self.covariances.transpose(), self.priors.transpose(),improved=True))
        
        testFeaMat = np.append(testFeaMat, temp[:,np.newaxis], axis=1)
        return testFeaMat

    def classify(self):
        testFeaMat = self._featuresExtraction()
        logreg = pickle.load(open('static/classificationModel/logregModel', 'rb'))
        prediction = logreg.predict(testFeaMat.T)
        if(prediction==1):
            result = "Meningioma"
        elif(prediction==2):
            result = "Glioma"
        elif(prediction==3):
            result = "Pituitary"
        return result, self.patientID, self.fileName, self.tumorSize

if __name__ == '__main__':
    fileData = '1.dcm'
    rawDataPath = '/home/faqih/ITB/TA/Web/server/static/rawData'
    maskDataPath = '/home/faqih/ITB/TA/Web/server/static/maskData'
    classifier = Classifier(fileData, rawDataPath, maskDataPath)
    prediction, patientID = classifier.classify()
    print(prediction)



