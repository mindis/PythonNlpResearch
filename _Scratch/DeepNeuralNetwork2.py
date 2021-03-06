'''
Created on Aug 18, 2013
@author: simon.hughes

Auto-encoder implementation. Can be used to implement a denoising auto-encoder, sparse or contractive auto-encoder
'''

import numpy as np
import gnumpy as gp
from numpy import matlib

USE_GPU = False

raise Exception("read this http://yyue.blogspot.ca/2015/01/a-brief-overview-of-deep-learning.html")

def get_array(a):
    if USE_GPU:
        if type(a) == gp.garray:
            return a
        return gp.garray(a)

    #ELSE NP
    if type(a) == np.array:
        return a
    return np.array(a)

def reverse_layers(layers):
    """ For flipping auto encoders and other deep networks,
        makes a copy of the layers but in reverse, sharing the weights and bias'

        layers = a list of Layer

        returns a list of Layer
    """
    rev_layers = []
    for i in range(len(layers)):
        layer = layers[i]
        bias = None if i == 0 else layers[i - 1].bias
        l = Layer(layer.num_outputs, layer.num_inputs, activation_fn=layer.activation_fn, weights=layer.weights.T,
                  bias=bias)
        rev_layers.insert(0, l)
    return rev_layers

class Layer(object):
    def __init__(self, num_inputs, num_outputs, activation_fn="tanh", initial_wt_max=0.01, weights=None, bias=None):
        self.activation_fn = activation_fn
        self.num_outputs = num_outputs
        self.num_inputs = num_inputs

        if weights is None:
            weights = get_array(matlib.rand((num_outputs, num_inputs)) * 2 * initial_wt_max) - initial_wt_max

        if bias is None:
            if self.activation_fn == "relu":
                # enforce positive
                bias = np.ones((num_outputs, 1)) * initial_wt_max
            else:
                bias = get_array(matlib.rand((num_outputs, 1)) * 2 * initial_wt_max) - initial_wt_max

        self.initial_wt_max = initial_wt_max
        self.weights        = weights
        self.bias           = bias

        #Force creation of best weights\bias
        self.save_state()

        assert self.num_inputs == self.weights.shape[1]
        assert self.num_outputs == self.weights.shape[0]
        assert self.num_outputs == self.bias.shape[0]

    def clone(self):
        return Layer( self.num_inputs, self.num_outputs, self.activation_fn, self.initial_wt_max, self.best_weights.copy(), self.best_bias.copy())

    def save_state(self):
        self.best_weights   = self.weights.copy()
        self.best_bias      = self.bias.copy()

    def revert_state(self):
        self.weights        = self.best_weights.copy()
        self.bias           = self.best_bias.copy()

    # for prediction (for case like dropout where we need to do something different
    # here by overriding this function
    def feed_forward(self, inputs_T):
        z = self.__compute_z__(inputs_T, self.best_weights, self.best_bias)
        a = self.__activate__(z, self.activation_fn)
        return (z, a)

    # for training
    def prop_up(self, inputs_T):

        """ Compute activations """
        z = self.__compute_z__(inputs_T, self.weights, self.bias)
        a = self.__activate__(z, self.activation_fn)
        return (z, a)

    def update(self, wtdiffs, biasdiff):

        self.weights -= wtdiffs
        self.bias    -= biasdiff

    def derivative(self, activations):

        if self.activation_fn == "sigmoid":
            """ f(z)(1 - f(z)) """
            return np.multiply(activations, (1.0 - activations))
        elif self.activation_fn == "softmax":
            # So long as we correctly compute the soft max output, derivative is linear
            return 1.0

        elif self.activation_fn == "tanh":
            """ 1 - f(z)^2 """
            return 1.0 - np.square(activations)
        elif self.activation_fn == "linear":
            return 1.0
        elif self.activation_fn == "relu":
            copy = activations.copy() # don't modify vector
            copy[copy < 0] = 0
            copy[copy > 0] = 1.0
            return copy
        else:
            raise NotImplementedError("Only sigmoid, tanh, linear and relu currently implemented")

    def __compute_z__(self, inputs_T, weights, bias):
        #Can we speed this up by making the bias a column vector?
        return np.dot(weights, inputs_T) + bias

    def __activate__(self, zs, activation_fn):

        if activation_fn == "sigmoid":
            return 1 / (1 + np.exp(-zs))

        elif activation_fn == "softmax":
            exponents = np.exp(zs)
            totals = exponents.sum(axis=0)
            if len(totals.shape) == 1:
                totals = totals.reshape((1, len(totals)))
            return exponents / totals

        elif activation_fn == "tanh":
            return np.tanh(zs)
        elif activation_fn == "linear":
            return zs
        elif activation_fn == "relu":
            copy = zs.copy()
            copy[copy < 0] = 0
            return copy
        else:
            raise NotImplementedError("Only sigmoid, tanh, softmax, linear and relu currently implemented")

def dropout_mask(shape, drop_out_prob):
    mask = np.matlib.rand(shape)
    mask[mask >= drop_out_prob] = 1.0
    mask[mask <  drop_out_prob] = 0.0
    return mask

class DropoutLayer(Layer):
    def __init__(self, num_inputs, num_outputs, activation_fn="tanh", drop_out_prob = 0.5, initial_wt_max=0.01, weights=None, bias=None):
        Layer.__init__(self, num_inputs, num_outputs, activation_fn, initial_wt_max, weights, bias)
        self.drop_out_prob = drop_out_prob
        self.mask = None
        self.freeze_mask = False

    def freeze_dropout_mask(self):
        self.freeze_mask = True
        self.mask = None

    def unfreeze_dropout_mask(self):
        self.freeze_mask = False

    def clone(self):
        layer =  DropoutLayer(self.num_inputs, self.num_outputs, self.activation_fn, self.drop_out_prob, self.initial_wt_max,
                              self.best_weights.copy(),self.best_bias.copy())
        layer.freeze_mask = self.freeze_mask
        layer.mask = self.mask
        return layer

    def feed_forward(self, inputs_T):
        # scale down outputs
        if self.freeze_mask:
            return self.prop_up(inputs_T)
        z,a  = Layer.feed_forward(self, inputs_T)
        a_d = a * (1.0 - self.drop_out_prob)
        return (z,a_d)

    def prop_up(self, inputs_T):
        z = self.__compute_z__(inputs_T, self.weights, self.bias)
        a = self.__activate__(z, self.activation_fn )
        if not self.freeze_mask or self.mask is None:
            mask = dropout_mask(a.shape , self.drop_out_prob)
            self.mask = mask
        else:
            mask = self.mask
        ad = np.multiply(a, mask)
        return (z,ad)

    def revert_state(self):
        pass

class MLP(object):
    '''
    classdocs
    '''

    def __init__(self, layers, input_drop_out_rate = 0.0, learning_rate=0.1, weight_decay=0.0, epochs = 50, batch_size = 32,
                 lr_increase_multiplier = 1.0, lr_decrease_multiplier = 1.0):
        '''
        learning_rate           = the learning rate
        weight_decay            = a regularization term to stop over-fitting. Only turn on if network converges too fast or overfits the data
        epochs                  = number of epochs to train for. Can be overridden when calling fit
        batch_size              = mini batch size. Can be overridden when calling fit
        lr_increase_multiplier  = factor used to multiply the learning rate by if error decreeases
        lr_decrease_multiplier  = factor used to multiply the learning rate by if error increases
        '''

        """ Properties """
        self.layers = layers
        self.learning_rate = learning_rate
        self.weight_decay = weight_decay
        self.epochs = epochs
        self.batch_size = batch_size
        self.lr_increase_multiplier = lr_increase_multiplier
        self.lr_decrease_multiplier = lr_decrease_multiplier
        self.input_drop_out_rate = input_drop_out_rate
        """ END Properties """
        self.lst_mse = []
        self.lst_mae = []

    def predict(self, inputs, layer_ix = np.inf, layers = None):
        if layers is None:
            layers = self.layers
        a = self.__ensure_vector_format__(inputs).T

        if self.input_drop_out_rate > 0.0:
            a = a * (1.0 - self.input_drop_out_rate)

        for i, layer in enumerate(layers):
            z, a = layer.feed_forward(a)
            if i == layer_ix:
                break
        return a.T

    def fit(self, xs, ys, epochs = None, batch_size = None):

        if epochs is None:
            epochs = self.epochs
        if batch_size is None:
            batch_size = self.batch_size

        inputs  = self.__ensure_vector_format__(xs)
        outputs = self.__ensure_vector_format__(ys)

        num_rows = inputs.shape[0]

        """ Number of rows in inputs should match those in outputs """
        assert inputs.shape[0] == outputs.shape[0], "Xs and Ys do not have the same row count"

        assert inputs.shape[1]  == self.layers[0].weights.shape[1],  "The input layer does not match the Xs column count"
        assert outputs.shape[1] == self.layers[-1].weights.shape[0], "The output layer does not match the Ys column count"

        """ Check outputs match the range for the activation function for the layer """
        self.__validate__(outputs, self.layers[-1])

        num_batches = num_rows / batch_size
        if num_rows % batch_size > 0:
            num_batches += 1

        mse = -1.0
        mae = -1.0

        ixs = range(len(xs))
        for epoch in range(epochs):

            """ Shuffle the dataset on each epoch """
            np.random.shuffle(ixs)
            inputs = inputs[ixs]
            outputs = outputs[ixs]
            """ Note that the error may start increasing exponentially at some point
                if so, halt training
            """

            errors = []
            for batch in range(num_batches):
                start = batch * batch_size
                end = start + batch_size
                mini_batch_in = inputs[start:end]
                mini_batch_out = outputs[start:end]
                if len(mini_batch_in) == 0:
                    continue

                mini_batch_errors, gradients = self.__compute_gradient__(mini_batch_in, mini_batch_out, len(xs),
                                                                         self.layers, self.learning_rate, self.weight_decay)
                if np.any(np.isnan(mini_batch_errors)):
                    print "Nans in errors. Stopping"
                    self.__reset_layers__()
                    return (mse, mae)

                errors.extend(mini_batch_errors)

                # apply weight updates
                for layer, gradient in zip(self.layers, gradients):
                    wds, bds = gradient
                    layer.update(wds, bds)

            errors = get_array(errors)
            mse = np.mean(np.square(errors))
            mae = np.mean(np.abs(errors))

            DIGITS = 6
            print "MSE for epoch {0} is {1}".format(epoch, np.round(mse,DIGITS)),
            print "\tMAE for epoch {0} is {1}".format(epoch, np.round(mae,DIGITS)),
            print "\tlearning rate is {0}".format(self.learning_rate)

            if len(self.lst_mae) > 0:
                self.__adjust_learning_rate__(self.lst_mae[-1], mae)
            self.lst_mse.append(mse)
            self.lst_mae.append(mae)
        return (mse, mae)

    """ Gradient Checking """
    def estimate_gradient(self, xs, ys, layers = None, epsilon = 0.0001):

        if layers is None:
            layers = self.layers[::]


        loss_type = "mse"
        if layers[-1].activation_fn == "softmax":
            loss_type = "crossentropy"

        layer_gradient = []
        for ix,l in enumerate(layers):
            wgrad = np.zeros(l.best_weights.shape)
            bgrad = np.zeros(l.best_bias.shape)

            layer_gradient.append((wgrad, bgrad))

            for i in range(l.best_weights.shape[0]):
                for j in range(l.best_weights.shape[1]):

                    p_clone = l.clone()
                    n_clone = l.clone()

                    p_layers = layers[::]
                    p_layers[ix] = p_clone

                    n_layers = layers[::]
                    n_layers[ix] = n_clone

                    p_clone.best_weights[i,j] += epsilon
                    n_clone.best_weights[i,j] -= epsilon


                    p_loss = self.loss(xs, ys, p_layers, loss_type=loss_type )
                    n_loss = self.loss(xs, ys, n_layers, loss_type=loss_type)
                    wgrad[i,j] = ((p_loss - n_loss) / (2 * epsilon)).sum()

            for i in range(len(l.best_bias)):
                p_clone = l.clone()
                n_clone = l.clone()

                p_layers = layers[::]
                p_layers[ix] = p_clone

                n_layers = layers[::]
                n_layers[ix] = n_clone

                p_clone.best_bias[i] += epsilon
                n_clone.best_bias[i] -= epsilon

                p_loss = self.loss(xs, ys, p_layers, loss_type=loss_type)
                n_loss = self.loss(xs, ys, n_layers, loss_type=loss_type)
                bgrad[i] = ((p_loss - n_loss) / (2 * epsilon)).sum()

        return layer_gradient

    def loss(self, input_vectors, outputs, layers = None, loss_type="mse"):

        # Note that this function does not transpose the inputs or outputs
        # Each row is a separate example \ label (i.e. row not column vectors)
        if layers is None:
            layers = self.layers

        predictions = self.predict(input_vectors, layers=layers)

        # error loss
        if loss_type == "mse":
            errors = predictions - outputs
            error_loss = (0.5 * ( np.multiply(errors, errors) )).mean(axis=0)
        elif loss_type == "crossentropy":
            error_loss = -((np.multiply(  outputs , np.log(predictions))).sum(axis=1).mean())
        else:
            raise Exception("Unknown loss type: " + loss_type)

        # weight decay loss
        sum_wts = 0.0
        for l in layers:
            sum_wts += ( np.multiply(l.best_weights ,l.best_weights )).sum()
        weight_decay_loss = (self.weight_decay / 2.0) * sum_wts

        # return combined loss function
        return error_loss + weight_decay_loss

    def verify_gradient(self, xs, ys):

        epsilon = 0.0001

        xs_copy = xs.copy()
        for l in self.layers:
            if type(l) == DropoutLayer:
                l.freeze_dropout_mask()

        if self.input_drop_out_rate > 0.0:
            mask = dropout_mask(xs.T.shape, self.input_drop_out_rate)
            xs_copy = np.multiply(xs_copy.T, mask).T
        else:
            mask = None

        errors, grad = self.__compute_gradient__(xs_copy, ys, len(xs), self.layers, 1.0, self.weight_decay, drop_out_mask=mask)
        grad_est = self.estimate_gradient(xs_copy, ys, self.layers, epsilon)

        for i in range(len(grad)):
            wdelta, bdelta = grad[i]
            est_wdelta, est_bdelta = grad_est[i]

            assert np.max(np.abs( wdelta - est_wdelta )) <= epsilon, "Significant Difference in estimated versus computed weights gradient"
            assert np.max(np.abs( bdelta - est_bdelta )) <= epsilon, "Significant Difference in estimated versus computed bias gradient"

        for l in self.layers:
            if type(l) == DropoutLayer:
                l.unfreeze_dropout_mask()

        print "Gradient is correct"

    """ END Gradient Checking """
    def __compute_gradient__(self, input_vectors, outputs, total_rows, layers, learning_rate, weight_decay, drop_out_mask = None):

        rows = input_vectors.shape[0]
        inputs_T = input_vectors.T.copy()

        if self.input_drop_out_rate > 0.0:
            if drop_out_mask is not None:
                mask = drop_out_mask
            else:
                mask = dropout_mask(inputs_T.shape, self.input_drop_out_rate)
            inputs_T = np.multiply(mask, inputs_T)

        outputs_T = outputs.T

        activations = [] # f(Wt.x)
        zs = []          # Wt.x
        derivatives = [] #f'(Wt.x)

        a = inputs_T
        for layer in layers:
            z, a = layer.prop_up(a)
            deriv = layer.derivative(a)
            activations.append(a)
            zs.append(z)
            derivatives.append(deriv)

        top_layer_output = activations[-1]
        """ errors = mean( 0.5 sum squared error)  """
        assert outputs_T.shape == top_layer_output.shape
        errors = (outputs_T - top_layer_output)

        # Compute weight updates
        delta =  np.multiply( -(errors), derivatives[-1])

        deltas = [delta]
        for i in range(len(layers) -1):
            ix = -(i + 1)
            layer = layers[ix]
            """ THIS IS BACK PROP OF ERRORS TO HIDDEN LAYERS"""
            delta = np.multiply( np.dot(layer.weights.T, delta) , derivatives[ix-1])
            deltas.insert(0, delta)

        #TODO Sparsity
        frows = float(rows)
        batch_proportion = frows / float(total_rows)

        gradients = []
        for i, layer in enumerate(layers):
            delta = deltas[i]
            activation_T = input_vectors if i == 0 else activations[i-1].T
            activation_T = np.asmatrix(activation_T)

            if type(layer) == DropoutLayer:
                #Compute input by input, as drop out mask differs by input
                wds  = np.zeros(layer.weights.shape)
                bds = np.zeros(layer.bias.shape)
                for j in range(delta.shape[1]):
                    wtdelta   = delta[:, j].dot(activation_T[j, :])
                    biasdiff = learning_rate * delta[:, j]
                    if weight_decay > 0.0:
                        wtdiffs = learning_rate * batch_proportion * (wtdelta + weight_decay * layer.weights)
                    else:
                        wtdiffs = learning_rate * batch_proportion * wtdelta

                    wds += np.multiply(wtdiffs, layer.mask[:, j])
                    bds += biasdiff / frows
            else:
                wtdelta = ((np.dot(delta, activation_T)) / (frows))
                """ As the inputs are always 1 then the activations are omitted for the bias """
                biasdelta = ((np.sum(delta, axis=1, keepdims=True) / (frows)))
                if weight_decay > 0.0:
                    wds = learning_rate * batch_proportion * (wtdelta + weight_decay * layer.weights)
                else:
                    wds = learning_rate * batch_proportion * wtdelta
                bds = learning_rate * biasdelta
            gradients.append((wds, bds))

        """ return a list of errors (one item per row in mini batch) """
        return (errors.T, gradients)

    def __reset_layers__(self):
        for layer in self.layers:
            layer.revert_state()

    def __adjust_learning_rate__(self, previous_mae, mae):
        # error improved on the training data?
        if mae <= previous_mae:
            self.learning_rate *= self.lr_increase_multiplier
            for layer in self.layers:
                layer.save_state()
        else:
            #print "MAE increased from %s to %s. Decreasing learning rate from %s to %s" % \
            #      (str(previous_mae), str(mae),
            #       str(self.learning_rate), str(self.learning_rate * self.lr_decrease_multiplier))
            self.learning_rate *=  self.lr_decrease_multiplier
            self.__reset_layers__()
        # restrict learning rate to sensible bounds
        self.learning_rate = max(0.001, self.learning_rate)
        self.learning_rate = min(1.000, self.learning_rate)

    def __ensure_vector_format__(self, a):
        return get_array(a)

    def __validate__(self, outputs, layer):

        min_outp = np.min(outputs)
        max_outp = np.max(outputs)

        if layer.activation_fn == "sigmoid":
            self.__in_range__(min_outp, max_outp, 0.0, 1.0)
        elif layer.activation_fn == "softmax":
            unique = set(outputs.flatten())
            assert len(unique) == 2,                                "Wrong number of outputs. Outputs for softmax must be 0's and 1's"
            assert min(unique) == 0 and max(unique) ==1,            "Outputs for softmax must be 0's and 1's only"
            assert np.all(outputs.sum(axis=1) == 1.0),              "Outputs for a softmax layer must sum to 1."

        elif layer.activation_fn == "tanh":
            self.__in_range__(min_outp, max_outp, -1.0, 1.0)
        elif layer.activation_fn == "relu":
            self.__in_range__(min_outp, max_outp, 0.0, np.inf)
        elif layer.activation_fn == "linear":
            pass
        else:
            raise Exception("Unknown activation function %s" % layer.activation_fn)

    def __in_range__(self, actual_min, actual_max, exp_min, exp_max):
        assert actual_max <= exp_max
        assert actual_min >= exp_min


if __name__ == "__main__":

    """
    # Test Sum
    xs = [
          [1,    0,     0.5,    0.1],
          [0,    1,     1.0,    0.5],
          [1,    0.5,   1,      0  ],
          [0,    0.9,   0,      1  ],
          [0.25, 0,     0.5,    0.1],
          [0.1,  1,     1.0,    0.5],
          [1,    0.5,   0.65,   0  ],
          [0.7,  0.9,   0,      1  ]
    ]


    # Identity - can memorize inputs ?
    xs = [
        [1, 0, 0, 0, 0, 0, 0, 0],
        [0, 1, 0, 0, 0, 0, 0, 0],
        [0, 0, 1, 0, 0, 0, 0, 0],
        [0, 0, 0, 1, 0, 0, 0, 0],
        [0, 0, 0, 0, 1, 0, 0, 0],
        [0, 0, 0, 0, 0, 1, 0, 0],
        [0, 0, 0, 0, 0, 0, 1, 0],
        [0, 0, 0, 0, 0, 0, 0, 1]
    ]
    """

    xs = [
        [1, 0, 0, 0, 0, 0, 0, 0],
        [1, 1, 0, 0, 0, 0, 0, 0],
        [0, 0, 1, 1, 0, 0, 0, 0],
        [1, 0, 0, 1, 0, 0, 0, 0],
        [1, 0, 0, 0, 1, 0, 1, 0],
        [0, 0, 0, 0, 0, 1, 0, 0],
        #[0, 1, 0, 0, 1, 0, 1, 0],
        #[1, 0, 1, 0, 1, 0, 0, 1]
    ]
    xs = np.array(xs)

    input_activation_fn  = "relu"
    output_activation_fn = "tanh"

    if input_activation_fn == "tanh":
        xs = (xs - 0.5) * 2.0

    ys = np.sum(xs, axis=1, keepdims=True) * 1.0
    ys = (ys - np.min(ys)) / (np.max(ys) - np.min(ys))
    ys = get_array(ys)
    """ Test as an Auto Encoder """
    soft_max_ys = []
    for x in xs:
        l = [0 for i in x]
        l[int(sum(x)) - 1] = 1
        soft_max_ys.append(l)
    soft_max_ys = get_array(soft_max_ys)

    ys = xs
    #ys = soft_max_ys

    if output_activation_fn == "tanh" and np.min(ys.flatten()) == 0.0:
        ys = (ys - 0.5) * 2.0

    #num_hidden = int(round(np.log2(xs.shape[1]))) + 1
    num_hidden = int(xs.shape[1] * 1.2)

    layers = [
        DropoutLayer(xs.shape[1], num_hidden,  activation_fn = input_activation_fn,  initial_wt_max=0.01, drop_out_prob=0.1),
        #Layer(num_hidden,  num_hidden,  activation_fn = input_activation_fn,  initial_wt_max=0.01),
        #Layer(num_hidden,  num_hidden,  activation_fn = input_activation_fn,  initial_wt_max=0.01),
        Layer(num_hidden,  ys.shape[1], activation_fn = output_activation_fn, initial_wt_max=0.01),
        ]


    """ Note that the range of inputs for tanh is 2* sigmoid, and so the MAE should be 2* """
    nn = MLP(layers, input_drop_out_rate=0.0,
             learning_rate=0.5, weight_decay=0.0, epochs=100, batch_size=6,
             lr_increase_multiplier=1.1, lr_decrease_multiplier=0.9)

    nn.fit(     xs, ys, epochs=100)

    """ Verify Gradient Calculation """
    #errors, grad = nn.__compute_gradient__(xs, ys, xs.shape[0], nn.layers, 1.0, nn.weight_decay)
    #grad_est = nn.estimate_gradient(xs, ys)

    #if not np.any([type(l) == DropoutLayer for l in layers]) and nn.input_drop_out_rate == 0.0:
    nn.verify_gradient(xs, ys)

    hidden_activations = nn.predict(xs, 0)
    predictions = nn.predict(xs)

    if output_activation_fn == "tanh":
        ys = ys / 2.0 + 0.5
        predictions = predictions / 2.0 + 0.5

    print "ys"
    print np.round(ys, 1) * 1.0
    print "predictions"
    #print np.round(ae.prop_up(xs, xs)[0] * 3.0) * 0.3
    print np.round(predictions, 1)
    print predictions
    print "Weights"
    print nn.layers[0].weights
    print ""
    print nn.layers[1].weights
    pass

    """ TODO
    implement momentum (refer to early parts of this https://www.cs.toronto.edu/~hinton/csc2515/notes/lec6tutorial.pdf)
    implement DROPOUT
    use LBFGS or conjugate gradient descent to optimize the parameters instead as supposedly faster

    >>>> DONE allow different activation functions per layer. Normally hidden layer uses RELU and dropout (http://fastml.com/deep-learning-these-days/)
          don't use RELU for output layer as you cannot correct for errors (i.e. gradient is 0 for negative updates!)
    >>>> DONE implement adaptive learning rate adjustments (see link above)
    >>>> DONE Use finite gradients method to verify gradient descent calc. Bake into code as a flag ***
    """